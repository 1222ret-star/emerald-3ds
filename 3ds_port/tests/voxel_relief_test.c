/* The shipped relief.bin, read by the runtime: a ledge's lip on Route 101.
 *
 * argv[1] is Route 101's layout id. Cell (3, 7) is one of the south ledge's
 * middle pieces (metatile 0x87): its lip's top edge, lattice row 2 (pixel row
 * 8), stands LIP (6) pixels up, its foot on the cell's south edge and the
 * ground behind it at its north edge stay on the ground; the walkable cell
 * north of it is not lifted at all.
 *
 * argv[2] is Route 116's, a map read off its drawing: cell (60, 2) is on the
 * mountain's top terrace, level, more than three levels up, and as far south
 * as it is high, like every point of the drawing.
 *
 * argv[3] is Rusturf Tunnel's, a cave carved out of the rock by hand
 * (relief_fixes.json): its belt stands three courses, as high as the rock
 * at its edges (cell (0, 0)); the corridor (5, 4) is a level up from the
 * west room's floor (4, 8), which is the base and not lifted. */
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>

#include "voxel_relief.h"

static const VoxelMapInstance *sOnly;

const VoxelMapInstance *VoxelWorld_GetInstanceAt(int x, int y)
{
    (void)x; (void)y;
    return sOnly;
}

int main(int argc, char **argv)
{
    VoxelMapInstance inst = {0};
    const int16_t *g;

    assert(argc == 4);
    inst.layoutId = atoi(argv[1]);
    assert(VoxelRelief_Init());
    g = VoxelRelief_Cell(&inst, 3, 7);
    assert(g != NULL && VoxelRelief_IsSlope(g));
    assert(g[2 * VOXEL_RELIEF_SIDE + 2] == 6);
    assert(g[4 * VOXEL_RELIEF_SIDE + 2] == 0);
    assert(g[0 * VOXEL_RELIEF_SIDE + 2] == 0);
    assert(g[3 * VOXEL_RELIEF_SIDE + 2] > 0 && g[3 * VOXEL_RELIEF_SIDE + 2] < 6);
    assert(VoxelRelief_Cell(&inst, 3, 6) == NULL);
    /* the same cell of a map with no relief is not lifted */
    inst.layoutId = 0;
    assert(VoxelRelief_Cell(&inst, 3, 7) == NULL);
    /* the drawn mountain */
    inst.layoutId = atoi(argv[2]);
    assert(VoxelRelief_IsDrawn(&inst));
    g = VoxelRelief_Cell(&inst, 60, 2);
    assert(g != NULL && !VoxelRelief_IsSlope(g) && g[0] > 48);
    assert(VoxelRelief_Depth(&inst, 60, 2) != NULL);
    assert(!VoxelRelief_IsSlope(VoxelRelief_Depth(&inst, 60, 2)));
    assert(VoxelRelief_Depth(&inst, 60, 2)[0] == g[0]);
    assert(VoxelRelief_CellShift(&inst, 60, 2) == VoxelRelief_CellLift(&inst, 60, 2));
    /* and the sun meets it where it stands, as far south as it is high */
    sOnly = &inst;
    assert(VoxelRelief_DrawnTop(&inst) >= g[0] / 16.0f);
    assert(fabsf(VoxelRelief_SurfaceAt(60.5f, 2.5f + g[0] / 16.0f) - g[0] / 16.0f) < 0.1f);
    sOnly = NULL;
    assert(VoxelRelief_Belt(&inst) == 0);
    /* the carved cave and its belt */
    inst.layoutId = atoi(argv[3]);
    assert(VoxelRelief_IsDrawn(&inst));
    assert(VoxelRelief_Belt(&inst) == 3);
    g = VoxelRelief_Cell(&inst, 0, 0);
    assert(g != NULL && !VoxelRelief_IsSlope(g) && g[0] == 16 * 3);
    g = VoxelRelief_Cell(&inst, 5, 4);
    assert(g != NULL && !VoxelRelief_IsSlope(g) && g[0] == 16);
    assert(VoxelRelief_Cell(&inst, 4, 8) == NULL);
    VoxelRelief_Shutdown();
    puts("PASS relief: ledge lip, a drawn terrace and a carved cave's belt from the ROMFS file, searched in row order");
    return 0;
}
