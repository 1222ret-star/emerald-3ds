"""Validate authored glass masks and the production VXB7/VXB8 page reader."""

import argparse
from pathlib import Path
import struct
import subprocess
import sys
import tempfile

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from voxel_night import window_mask, NIGHT_WINDOWS


def mask_tests():
    art = Image.new("RGBA", (8, 8), (65, 74, 106, 255))
    art.putpixel((2, 2), (189, 205, 230, 255))
    art.putpixel((3, 2), (156, 180, 222, 255))
    art.putpixel((4, 2), (213, 197, 106, 255))
    art.putpixel((2, 3), (189, 205, 230, 0))
    art.putpixel((7, 7), (189, 205, 230, 255))
    original = art.tobytes()
    mask = window_mask(art, ((1, 1, 6, 6),))
    assert [index for index, value in enumerate(mask) if value] == [18, 19]
    assert mask[18] > mask[19] > 0
    assert not any(window_mask(art, ()))
    assert original == art.tobytes()
    try:
        window_mask(art, ((0, 0, 9, 8),))
    except ValueError:
        pass
    else:
        raise AssertionError("out-of-bounds window accepted")
    assert "kit_house_4" in NIGHT_WINDOWS and "kit_house_5" in NIGHT_WINDOWS


def reader_tests(cc):
    source = r'''
#include <assert.h>
#include <stdint.h>
#include "voxel_building.h"
void VoxelGrade_Texels(uint16_t *pixels, unsigned count) { (void)pixels; (void)count; }
int main(int argc, char **argv)
{
    unsigned width, height;
    uint16_t pixels[64];
    uint8_t mask[64];
    assert(argc == 2);
    assert(VoxelBuildings_Init());
    assert(VoxelBuildings_PageSize(0, &width, &height) && width == 8 && height == 8);
    assert(!VoxelBuildings_PageSize(1, &width, &height));
    assert(VoxelBuildings_ReadPage(0, 0, 64, pixels));
    assert(pixels[0] == 0xFFFF && pixels[63] == 0xFFFF);
    assert(!VoxelBuildings_ReadPage(0, UINT32_MAX, 2, pixels));
    assert(VoxelBuildings_PageHasGlow(0) == (argv[1][0] != '0'));
    assert(!VoxelBuildings_PageHasGlow(1));
    if (argv[1][0] == '1')
    {
        assert(VoxelBuildings_ReadGlow(0, 0, 64, mask));
        for (unsigned index = 0; index < 64; ++index) assert(mask[index] == index);
        assert(VoxelBuildings_ReadGlow(0, 17, 9, mask) && mask[0] == 17 && mask[8] == 25);
        assert(!VoxelBuildings_ReadGlow(0, UINT32_MAX, 2, mask));
        assert(!VoxelBuildings_ReadGlow(1, 0, 1, mask));
    }
    else if (argv[1][0] == '2') assert(!VoxelBuildings_ReadGlow(0, 0, 64, mask));
    else assert(!VoxelBuildings_ReadGlow(0, 0, 1, mask));
    VoxelBuildings_Shutdown();
    assert(!VoxelBuildings_PageHasGlow(0));
    return 0;
}
'''
    with tempfile.TemporaryDirectory() as directory:
        temporary = Path(directory)
        (temporary / "test.c").write_text(source)
        subprocess.run([
            cc, "-std=c99", "-Wall", "-Wextra", "-Werror", "-ffunction-sections",
            "-fdata-sections", "-fsanitize=address,undefined", "-DVOXEL_HOST_FILES",
            "-DPORT_LOG(...)=((void)0)", '-DVOXEL_BUILDINGS_PATH="buildings.bin"',
            "-I" + str(ROOT / "src/voxel"), "-I" + str(ROOT / "include"),
            str(temporary / "test.c"), str(ROOT / "src/voxel/voxel_building.c"),
            "-Wl,-dead_strip" if sys.platform == "darwin" else "-Wl,--gc-sections",
            "-o", str(temporary / "test"),
        ], check=True)
        for magic, flag, truncated in ((b"VXB7", False, False), (b"VXB8", False, False),
                                       (b"VXB8", True, False), (b"VXB8", True, True)):
            header = magic + struct.pack("<HHHHHHIHH", 1, 0, 0, 0, 0, 0, 0, 0, 0)
            page = struct.pack("<HHI", 8, 8 | (0x8000 if flag else 0), 32)
            data = struct.pack("<64H", *([0xFFFF] * 64))
            if flag and not truncated:
                data += bytes(range(64))
            (temporary / "buildings.bin").write_bytes(header + page + data)
            subprocess.run([str(temporary / "test"), "1" if flag and not truncated else
                            "2" if flag else "0"], cwd=temporary, check=True)


def renderer_tests(cc):
    text = (ROOT / "src/voxel/ctr_voxel.c").read_text()
    functions = []
    for name in ("ReleaseGlowUnit", "BuildingGlowEnv"):
        start = text.index("static void " + name + "(")
        position = text.index("{", start) + 1
        depth = 1
        while depth:
            depth += (text[position] == "{") - (text[position] == "}")
            position += 1
        functions.append(text[start:position])
    source = r'''
#include <assert.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>
typedef struct { unsigned placeholder; } C3D_Tex;
typedef struct { int rgb[3], alpha[3], alphaOp[3], rgbOp[3], rgbFunc, alphaFunc; uint32_t colour; } C3D_TexEnv;
enum { C3D_RGB, C3D_Alpha, GPU_TEXTURE0, GPU_TEXTURE2, GPU_CONSTANT, GPU_PREVIOUS,
       GPU_TEVOP_A_SRC_R, GPU_TEVOP_A_SRC_ALPHA, GPU_MODULATE, GPU_TEVOP_RGB_SRC_COLOR,
       GPU_TEVOP_RGB_SRC_ALPHA, GPU_INTERPOLATE, GPU_REPLACE };
static uint8_t __C3D_Context[512] __attribute__((aligned(16)));
#define C3DI_CONTEXT_FLAGS 0x20u
#define C3DI_CONTEXT_TEX 0x118u
#define C3DI_FLAG_TEX(unit) (1u << (23 + (unit)))
static C3D_Tex sTreeAtlas, *sGlowBound;
static C3D_TexEnv sEnvs[6];
static int sBinds;
static C3D_TexEnv *C3D_GetTexEnv(unsigned index) { return &sEnvs[index]; }
static void TerrainTexEnv(void *unused) { (void)unused; memset(sEnvs, 0, sizeof(sEnvs)); }
static void C3D_TexBind(int unit, C3D_Tex *texture)
{
    assert(texture != NULL && unit == 2);
    ((C3D_Tex **)(void *)(__C3D_Context + C3DI_CONTEXT_TEX))[unit] = texture;
    ++sBinds;
}
static void C3D_TexEnvSrc(C3D_TexEnv *env, int mode, int first, int second, int third)
{
    int *values = mode == C3D_RGB ? env->rgb : env->alpha;
    values[0] = first; values[1] = second; values[2] = third;
}
static void C3D_TexEnvOpAlpha(C3D_TexEnv *env, int first, int second, int third)
{ env->alphaOp[0] = first; env->alphaOp[1] = second; env->alphaOp[2] = third; }
static void C3D_TexEnvOpRgb(C3D_TexEnv *env, int first, int second, int third)
{ env->rgbOp[0] = first; env->rgbOp[1] = second; env->rgbOp[2] = third; }
static void C3D_TexEnvFunc(C3D_TexEnv *env, int mode, int function)
{ if (mode == C3D_RGB) env->rgbFunc = function; else env->alphaFunc = function; }
static void C3D_TexEnvColor(C3D_TexEnv *env, uint32_t colour) { env->colour = colour; }
'''
    source += "\n".join(functions)
    source += r'''
int main(void)
{
    C3D_Tex mask, other;
    C3D_Tex **bound = (C3D_Tex **)(void *)(__C3D_Context + C3DI_CONTEXT_TEX);
    uint32_t *flags = (uint32_t *)(void *)(__C3D_Context + C3DI_CONTEXT_FLAGS);
    BuildingGlowEnv(NULL, 1.0f);
    BuildingGlowEnv(&mask, 0.0f);
    assert(sBinds == 0 && sGlowBound == NULL);
    BuildingGlowEnv(&mask, 0.5f);
    assert(sBinds == 1 && bound[2] == &mask && sGlowBound == &mask);
    assert(sEnvs[1].alpha[0] == GPU_TEXTURE2 && sEnvs[1].alpha[1] == GPU_CONSTANT);
    assert(sEnvs[1].alphaOp[0] == GPU_TEVOP_A_SRC_R);
    assert(sEnvs[1].alphaFunc == GPU_MODULATE && sEnvs[1].colour == 0x80000000u);
    assert(sEnvs[2].rgbFunc == GPU_INTERPOLATE && sEnvs[2].rgb[0] == GPU_CONSTANT);
    assert(sEnvs[2].rgb[1] == GPU_PREVIOUS && sEnvs[2].rgbOp[2] == GPU_TEVOP_RGB_SRC_ALPHA);
    assert(sEnvs[2].alpha[0] == GPU_TEXTURE0 && sEnvs[2].alphaFunc == GPU_REPLACE);
    assert(sEnvs[2].colour == 0xFFA0D8FFu);
    assert(sEnvs[3].colour == 0 && sEnvs[4].colour == 0);
    ReleaseGlowUnit();
    assert(bound[2] == NULL && sGlowBound == NULL && *flags == C3DI_FLAG_TEX(2));
    BuildingGlowEnv(&mask, 1.0f);
    bound[2] = &other;
    ReleaseGlowUnit();
    assert(bound[2] == &sTreeAtlas && sGlowBound == NULL);
    BuildingGlowEnv(&mask, 1.0f);
    BuildingGlowEnv(NULL, 1.0f);
    assert(bound[2] == NULL && sGlowBound == NULL && sEnvs[2].colour == 0);
    return 0;
}
'''
    with tempfile.TemporaryDirectory() as directory:
        temporary = Path(directory)
        (temporary / "render.c").write_text(source)
        subprocess.run([cc, "-std=c99", "-Wall", "-Wextra", "-Werror",
                        "-fsanitize=address,undefined", str(temporary / "render.c"),
                        "-o", str(temporary / "render")], check=True)
        subprocess.run([str(temporary / "render")], check=True)
    shader = (ROOT / "src/voxel/voxel.v.pica").read_text()
    assert ".out outtc2 texcoord2" in shader and "mov outtc2, intex" in shader
    assert "C3D_TexBind(2, NULL)" not in text


def asset_tests(path):
    data = path.read_bytes()
    assert data[:4] == b"VXB8"
    page_count = struct.unpack_from("<H", data, 4)[0]
    lit_count = 0
    for index in range(page_count):
        width, flagged_height, offset = struct.unpack_from("<HHI", data, 24 + index * 8)
        height = flagged_height & 0x7FFF
        pixels = width * height
        assert offset + pixels * 2 <= len(data)
        if flagged_height & 0x8000:
            lit_count += 1
            mask = data[offset + pixels * 2:offset + pixels * 3]
            assert len(mask) == pixels and any(mask)
            for pixel, value in enumerate(mask):
                if value:
                    assert struct.unpack_from("<H", data, offset + pixel * 2)[0] & 1
    assert lit_count > 0
    print("PASS night assets: %d glowing pages, opaque glass only" % lit_count)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cc", default="clang")
    parser.add_argument("--assets", type=Path)
    arguments = parser.parse_args()
    mask_tests()
    reader_tests(arguments.cc)
    renderer_tests(arguments.cc)
    if arguments.assets:
        asset_tests(arguments.assets)
    print("PASS night windows: masks, unchanged art, legacy pages, streaming slices, truncation, bounds")


if __name__ == "__main__":
    main()
