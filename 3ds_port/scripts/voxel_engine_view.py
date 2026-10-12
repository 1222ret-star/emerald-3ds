#!/usr/bin/env python3
"""A map as the console builds it, from the console's own code and data.

The previews of the modelling tools (townview, dev.py) draw the models from
the Python that made them; the console draws what the exporter wrote, as its
C code builds it, inside its budgets. When the two part (a buffer that
refuses triangles, a ground patch the exporter dropped, memory that runs out)
the preview says nothing. This one is built from tests/voxel_scene_dump.c:
the engine's builder, trees, buildings, relief and lighting, compiled for the
host over romfs/voxel/*.bin, chunk by chunk as ctr_voxel.c JobStep builds
them, at the console's capacity. What it shows is what the console has.

    python voxel_engine_view.py view LAYOUT X,Y OUT.png [--pitch 40]
                                [--yaw 0] [--dist 9] [--scale 2]
        the game's camera on cell X,Y
    python voxel_engine_view.py check [LAYOUT ...]
        every map (or those): chunks that refuse triangles (the console
        drops them: holes), static models over their memory budget; with
        no layouts also connected maps whose building pages cannot share
        the page arena. Exit 1 when any.

The dump is rebuilt when its sources are newer (msys2 mingw64 gcc).
"""

import argparse
import glob
import json
import math
import os
import shlex
import shutil
import struct
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import voxel_building as vb  # noqa: E402
import voxel_cells as vc  # noqa: E402
import voxel_relief_lines as vl  # noqa: E402
from PIL import Image  # noqa: E402

DUMP = os.path.join(PORT, "build", "voxel_scene_dump.exe")
SOURCES = ["tests/voxel_scene_dump.c"] + ["src/voxel/%s.c" % n for n in (
    "voxel_mesh_builder", "voxel_tree", "voxel_sign", "voxel_building", "voxel_relief",
    "voxel_grade", "voxel_lighting", "voxel_regions")] + ["src/3ds_video_decode.c"]
SCRATCH = 8192 + 64 * 18          # ctr_voxel.c VOXEL_CHUNK_SCRATCH
# A map's static models (ctr_voxel.c StaticBuildSlice), in the console's linear
# memory: what one map may hold at once, with room left for the rest of the
# game. Measured 2026-10-10: 517 KiB of linear memory free in Slateport, but
# not in one block (the lantern alone at 275 KiB did not fit); each model is
# its own block, the largest ~80 KiB. To confirm on the console: no "no
# linear memory" line in port.log.
STATIC_BUDGET = 160 * 1024
PAGE_ARENA = 768 * 1024           # ctr_voxel.c VOXEL_PAGE_VRAM_BUDGET
SHAPE_FLAT, SHAPE_WATER = 0, 7    # voxel_world.h VoxelVisualShape
SUN_DX, SUN_DZ, AMBIENT = 0.85, 0.55, 0.70
TREE_DIM = 128


def build_dump():
    srcs = [os.path.join(PORT, s) for s in SOURCES]
    deps = srcs + [os.path.abspath(__file__)] + glob.glob(os.path.join(PORT, "src", "voxel", "*.h")) \
        + glob.glob(os.path.join(PORT, "include", "*.h"))
    if os.path.exists(DUMP) and os.path.getmtime(DUMP) >= max(os.path.getmtime(d) for d in deps):
        return
    hostinc = os.path.join(PORT, "build", "hostinc")
    os.makedirs(hostinc, exist_ok=True)
    with open(os.path.join(hostinc, "port_log.h"), "w") as f:
        f.write("/* host build of the scene dump */\n#ifndef PORT_LOG\n#define PORT_LOG(...) ((void)0)\n#endif\n")
    compiler = shlex.split(os.environ.get("HOSTCC", "cc"), posix=os.name != "nt")
    compiler = [part.strip('"') for part in compiler]
    if not compiler or shutil.which(compiler[0]) is None:
        raise SystemExit("host compiler not found; set HOSTCC to a native C compiler")
    cmd = compiler + ["-std=c99", "-O2", "-I" + hostinc, "-Iinclude", "-Isrc/voxel",
           "-DPORT_LOG(...)=((void)0)", "-DCTR_VOXEL_LIGHTING=1", "-DVOXEL_HOST_FILES",
           '-DVOXEL_BUILDINGS_PATH="romfs/voxel/buildings.bin"',
           '-DVOXEL_RELIEF_PATH="romfs/voxel/relief.bin"',
           '-DVOXEL_REGIONS_PATH="romfs/voxel/regions.bin"',
           '-DSIGN_MASK_PATH="romfs/voxel/signposts.bin"'] + SOURCES + ["-lm", "-o", DUMP]
    if os.name != "nt":
        cmd.insert(len(compiler), "-D_POSIX_C_SOURCE=200809L")
    env = dict(os.environ)
    env["PATH"] = os.path.dirname(shutil.which(compiler[0])) + os.pathsep + env.get("PATH", "")
    r = subprocess.run(cmd, cwd=PORT, capture_output=True, text=True, env=env)
    if r.returncode:
        raise SystemExit("building the scene dump failed:\n" + r.stderr)


# ── the shipped buildings.bin ──────────────────────────────────────────────

class Buildings:
    """romfs/voxel/buildings.bin as the console reads it."""

    def __init__(self, path=None):
        with open(path or os.path.join(PORT, "romfs", "voxel", "buildings.bin"), "rb") as source:
            b = self.blob = source.read()
        if b[:4] not in (b"VXB7", b"VXB8"):
            raise ValueError("unsupported buildings format: %r" % b[:4])
        (npages, nmodels, npm, nplaces, hbytes, nmasks) = struct.unpack_from("<6H", b, 4)
        nverts, nvar = struct.unpack_from("<IH", b, 16)
        o = 24
        raw_pages = [struct.unpack_from("<HHI", b, o + 8 * i) for i in range(npages)]
        self.page_glow = [b[:4] == b"VXB8" and bool(height & 0x8000)
                          for width, height, offset in raw_pages]
        self.pages = [(width, height & 0x7FFF if b[:4] == b"VXB8" else height, offset)
                      for width, height, offset in raw_pages]
        o += npages * 8
        self.models = []
        for i in range(nmodels):
            w, h, ground, first, count, heights = struct.unpack_from("<BBHIII", b, o + 16 * i)
            self.models.append((w, h, first, count & 0x7FFFFFFF, bool(count & 0x80000000)))
        o += nmodels * 16
        self.page_models = [struct.unpack_from("<HHhh", b, o + 8 * i) for i in range(npm)]
        o += npm * 8 + nplaces * 16
        o += hbytes
        o += o & 1
        o += hbytes * 2 + nmasks * 32 + hbytes
        o += o & 1
        o += nvar * 6
        o += (-o) & 3
        self.vert_at = o
        self._pages = {}

    def page(self, k):
        """Page k's texture, decoded from the console's tiled RGBA5551."""
        if k not in self._pages:
            w, h, off = self.pages[k]
            img = Image.new("RGBA", (w, h))
            px = img.load()
            for y in range(h):
                for x in range(w):
                    t = struct.unpack_from("<H", self.blob, off + 2 * texel_offset(x, y, w))[0]
                    px[x, y] = ((t >> 11) << 3, ((t >> 6) & 31) << 3, ((t >> 1) & 31) << 3,
                                255 if t & 1 else 0)
            self._pages[k] = img
        return self._pages[k]

    def model_tris(self, page_model):
        """A static model's triangles as StaticBuildSlice packs them: page uv,
        lit by the sun's facing."""
        model, page, ox, oy = self.page_models[page_model]
        w, h, first, count, _ = self.models[model]
        pw, ph = self.pages[page][:2]
        out = []
        for k in range(0, count - count % 3, 3):
            vs = [struct.unpack_from("<6f", self.blob, self.vert_at + 24 * (first + k + j))
                  for j in range(3)]
            shade = model_shade(vs)
            out.append(tuple((x, y, z, (ox + u) / pw, 1.0 - (oy + v) / ph, shade)
                             for (x, y, z, u, v, s) in vs))
        return page, out


def texel_offset(x, y, width):
    morton = 0
    for bit in range(3):
        morton |= ((x >> bit) & 1) << (2 * bit) | ((y >> bit) & 1) << (2 * bit + 1)
    return ((y // 8) * (width // 8) + x // 8) * 64 + morton


def model_shade(vs):
    """voxel_lighting.c VoxelLighting_ModelShade."""
    a, b, c = vs
    ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    wx, wy, wz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
    nx, ny, nz = uy * wz - uz * wy, uz * wx - ux * wz, ux * wy - uy * wx
    s = a[5]
    if abs(s - 0.90) < 0.02:
        flip = False
    elif abs(s - 0.80) < 0.02:
        flip = nx > 0
    elif abs(s - 0.72) < 0.02:
        flip = nx < 0
    elif abs(s - 0.66) < 0.02:
        flip = ny + nz > 0
    else:
        flip = ny + nz < 0
    if flip:
        nx, ny, nz = -nx, -ny, -nz
    L = math.sqrt(nx * nx + ny * ny + nz * nz)
    if L <= 0:
        return 1.0
    f = (ny - SUN_DX * nx - SUN_DZ * nz) / L
    return AMBIENT if f <= 0 else 1.0 if f >= 1 else AMBIENT + (1 - AMBIENT) * f


def tree_atlas():
    blob = open(os.path.join(PORT, "romfs", "voxel", "trees.rgba5551"), "rb").read()
    img = Image.new("RGBA", (TREE_DIM, TREE_DIM))
    px = img.load()
    for y in range(TREE_DIM):
        for x in range(TREE_DIM):
            t = struct.unpack_from("<H", blob, 2 * texel_offset(x, y, TREE_DIM))[0]
            px[x, y] = ((t >> 11) << 3, ((t >> 6) & 31) << 3, ((t >> 1) & 31) << 3,
                        255 if t & 1 else 0)
    return img


# ── the dump ───────────────────────────────────────────────────────────────

def layout_entry(layout_id):
    L = vl.layouts()
    entry = next(e for e in L if e["id"] == layout_id)
    return entry, L.index(entry) + 1


def dump(layout_id):
    """[chunk dicts] of the layout as the console builds it."""
    build_dump()
    entry, index = layout_entry(layout_id)
    w, h = entry["width"], entry["height"]
    blocks = vb.read_u16(os.path.join(vb.ROOT, entry["blockdata_filepath"]))
    cells = vc.Layout(entry, vc.MapEvents())
    shapes = bytes(SHAPE_WATER if cells.behaviour(x, y) in vc.WATER else SHAPE_FLAT
                   for y in range(h) for x in range(w))
    primary, secondary = entry["primary_tileset"], entry["secondary_tileset"]
    indoor = primary != "gTileset_General"
    flags = (1 if indoor else 0) | (2 if primary == "gTileset_General" else 0) \
        | (4 if secondary == "gTileset_Dewford" else 0)
    tmp = os.path.join(PORT, "build", "scene_%s_%d" % (layout_id, os.getpid()))
    with open(tmp + ".in", "wb") as f:
        f.write(struct.pack("<HHHH", index, w, h, flags))
        f.write(struct.pack("<%dH" % (w * h), *[b_ & 0x3FF for b_ in blocks[:w * h]]))
        f.write(shapes)
    r = subprocess.run([DUMP, tmp + ".in", tmp + ".out"], cwd=PORT, capture_output=True, text=True)
    if r.returncode:
        raise SystemExit("voxel_scene_dump failed (%d): %s" % (r.returncode, r.stderr))
    data = open(tmp + ".out", "rb").read()
    os.remove(tmp + ".in")
    os.remove(tmp + ".out")
    n = struct.unpack_from("<I", data)[0]
    o = 4
    chunks = []
    for _ in range(n):
        cx, cy, count, dropped, terrain, first, nstat, page = struct.unpack_from("<hhIIIIIi", data, o)
        o += 28
        statics = []
        for _ in range(nstat):
            pm, lit, x, y, z = struct.unpack_from("<II3f", data, o)
            statics.append((pm, lit, (x, y, z)))
            o += 20
        verts = struct.unpack_from("<%df" % (count * 6), data, o)
        o += count * 24
        vs = [verts[i * 6:i * 6 + 6] for i in range(count)]
        chunks.append({"cx": cx, "cy": cy, "count": count, "dropped": dropped,
                       "terrain": terrain, "first": first, "page": page, "statics": statics,
                       "verts": vs})
    return chunks, index


# ── the picture ────────────────────────────────────────────────────────────

def view(args):
    chunks, index = dump(args.layout)
    atlas = vl.Atlas(args.layout)
    bld = Buildings()
    trees = tree_atlas()
    groups = {"atlas": [], "trees": [], }
    pages = {}
    for c in chunks:
        vs = c["verts"]
        for i in range(0, c["count"] - c["count"] % 3, 3):
            tri = tuple(vs[i:i + 3])
            if i < c["terrain"]:
                groups["atlas"].append(tri)
            elif i < c["first"]:
                groups["trees"].append(tri)
            else:
                pages.setdefault(c["page"], []).append(tri)
        for (pm, lit, (x, y, z)) in c["statics"]:
            page, tris = bld.model_tris(pm)
            pages.setdefault(page, []).extend(
                tuple((px + x, py + y, pz + z, u, v, s) for (px, py, pz, u, v, s) in t) for t in tris)
    at = tuple(int(v) for v in args.at.split(","))
    allt = groups["atlas"] + groups["trees"] + [t for ts in pages.values() for t in ts]
    cam = vl.camera(allt, at, args.pitch, args.dist, args.yaw)
    W, H = cam.width * args.scale, cam.height * args.scale
    cam2 = vb.Camera(cam.target, cam.pitch, cam.yaw, cam.distance, cam.fov, W, H)
    ras = vl.Raster(W, H, bg=(255, 0, 255))
    for t in groups["atlas"]:
        atlas.need(vl.atlas_id(t))
    S = vl.GRID * 16
    reach = cam.distance * 2.2

    def draw(tris, tex, uvmap):
        tpx = tex.load()
        for k, tri in enumerate(tris):
            mx = sum(p[0] for p in tri) / 3 - cam.target[0]
            mz = sum(p[2] for p in tri) / 3 - cam.target[2]
            if abs(mx) > reach or abs(mz) > reach:
                continue
            out = []
            for (x, y, z, u, v, s) in tri:
                pr = cam2.project((x, y, z))
                if pr is None:
                    break
                sx, sy, d, iw = pr
                tu, tv = uvmap(u, v)
                out.append((sx, sy, d, iw, tu * iw, tv * iw))
            else:
                ras.draw(out, tex, tpx, tri[0][5], k)

    draw(groups["atlas"], atlas.img, lambda u, v: (u * S, v * S))
    draw(groups["trees"], trees, lambda u, v: (u * TREE_DIM, (1.0 - v) * TREE_DIM))
    for page, tris in pages.items():
        if page < 0:
            continue
        img = bld.page(page)
        draw(tris, img, lambda u, v, img=img: (u * img.size[0], (1.0 - v) * img.size[1]))
    ras.image().save(args.out)
    bad = [(c["cx"], c["cy"], c["dropped"]) for c in chunks if c["dropped"]]
    print("%s: %d chunks, %d vertices%s" % (args.layout, len(chunks), sum(c["count"] for c in chunks),
                                           ", DROPPED in %s" % bad if bad else ""))


# ── the checks ─────────────────────────────────────────────────────────────

def static_bytes(bld, page_model):
    """The console's linear memory for one static model: shared vertices
    (16 bytes) and u16 indices (StaticBuildSlice)."""
    page, tris = bld.model_tris(page_model)
    seen = set()
    for t in tris:
        for p in t:
            seen.add(tuple(round(c, 4) for c in p))
    return len(seen) * 16 + len(tris) * 3 * 2


def layout_pages(bld):
    """Layout id (1-based) -> its page's (width, height), from the
    placements (one page a layout)."""
    b = bld.blob
    npages, nmodels, npm, nplaces = struct.unpack_from("<4H", b, 4)
    o = 24 + npages * 8 + nmodels * 16 + npm * 8
    out = {}
    for i in range(nplaces):
        lid, pm = struct.unpack_from("<HH", b, o + 16 * i)
        out[lid] = bld.pages[bld.page_models[pm][1]][:2]
    return out


def page_pairs(bld):
    """Maps joined by a connection stand in view together, and with them
    their pages in the console's page arena (ctr_voxel.c
    VOXEL_PAGE_VRAM_BUDGET): two that cannot share it leave one map without
    its buildings, retried for seconds, at the border. [(map, other, KiB)]
    over the arena."""
    layouts = json.load(open(os.path.join(vb.ROOT, "data", "layouts", "layouts.json")))["layouts"]
    lid_of = {e["id"]: k + 1 for k, e in enumerate(layouts) if e and "id" in e}
    sizes = layout_pages(bld)
    maps = {}
    for path in glob.glob(os.path.join(vb.ROOT, "data", "maps", "*", "map.json")):
        m = json.load(open(path))
        maps[m["id"]] = m
    bad = set()
    for m in maps.values():
        a = sizes.get(lid_of.get(m.get("layout")))
        for c in m.get("connections") or []:
            other = maps.get(c.get("map"))
            b = sizes.get(lid_of.get(other.get("layout"))) if other else None
            if a and b and a[0] * a[1] * 2 + b[0] * b[1] * 2 > PAGE_ARENA:
                pair = tuple(sorted((m["id"], other["id"])))
                bad.add(pair + ((a[0] * a[1] + b[0] * b[1]) * 2 >> 10,))
    return sorted(bad)


def check(args):
    names = args.layouts or [e["id"] for e in vl.layouts() if "id" in e
                             and e.get("primary_tileset") == "gTileset_General"]
    bld = Buildings()
    failed = False
    for name in names:
        try:
            chunks, _ = dump(name)
        except SystemExit as e:
            print("%-40s dump failed: %s" % (name, e))
            failed = True
            continue
        worst = max(chunks, key=lambda c: c["count"]) if chunks else None
        drops = [c for c in chunks if c["dropped"]]
        models = sorted({pm for c in chunks for (pm, lit, p) in c["statics"]})
        mem = sum(static_bytes(bld, pm) for pm in models)
        line = "%-40s fullest chunk %5d/%d" % (name, worst["count"] if worst else 0, SCRATCH)
        if drops:
            failed = True
            line += "  DROPS " + ", ".join("%d,%d:%d tris" % (c["cx"] * 8, c["cy"] * 8, c["dropped"])
                                           for c in drops)
        if models:
            line += "  static %d model(s) %d KiB" % (len(models), mem >> 10)
            if mem > STATIC_BUDGET:
                failed = True
                line += " OVER %d KiB" % (STATIC_BUDGET >> 10)
        if drops or models or args.verbose:
            print(line)
    if not args.layouts:
        for (a, b, kib) in page_pairs(bld):
            failed = True
            print("%s + %s: building pages %d KiB, OVER the %d KiB page arena"
                  % (a, b, kib, PAGE_ARENA >> 10))
    print("FAILED" if failed else "ok")
    return 1 if failed else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("view")
    v.add_argument("layout")
    v.add_argument("at")
    v.add_argument("out")
    v.add_argument("--pitch", type=float, default=40.0)
    v.add_argument("--yaw", type=float, default=0.0)
    v.add_argument("--dist", type=float, default=9.0)
    v.add_argument("--scale", type=int, default=2)
    c = sub.add_parser("check")
    c.add_argument("layouts", nargs="*")
    c.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    if args.cmd == "view":
        view(args)
        return 0
    return check(args)


if __name__ == "__main__":
    sys.exit(main())
