/* Clock-driven sun, baked into chunk colours; no extra terrain GPU pass. */
#ifndef CTR_VOXEL_LIGHTING_H
#define CTR_VOXEL_LIGHTING_H

#include "voxel_mesh_builder.h"

/* Standalone host consumers retain the original mesh unless explicitly enabled. */
#ifndef CTR_VOXEL_LIGHTING
#define CTR_VOXEL_LIGHTING 0
#endif

#if CTR_VOXEL_LIGHTING
/* The legacy sun is northwest; AUTO follows the clock. Y is height. */
typedef struct
{
    float dx, dz, strength;
    uint32_t key;
} VoxelSun;
extern VoxelSun gVoxelSun;
#define VOXEL_SUN_DX (gVoxelSun.dx)
#define VOXEL_SUN_DZ (gVoxelSun.dz)
#define VOXEL_LIGHT_REACH 8
/* The light of what the sun does not reach: a cast shadow, and a face turned
 * away from the sun. The same number, so a wall and the shadow it casts on
 * the grass read as the same shade. */
#define VOXEL_AMBIENT 0.70f
/* Four clipped octagons, at most twelve vertices / ten triangles each. */
#define VOXEL_CONTACT_VERTICES 120u

/* Forgets every cached caster and sample. Required whenever the world they
 * were read from changes - a live tile, the set of maps or their origins -
 * and needed at no other time: the caches outlive builds and frames. */
void VoxelLighting_Reset(void);
bool VoxelLighting_SetSun(float dx, float dz, float strength, uint32_t key);
uint32_t VoxelLighting_Hash(int x0, int z0, int x1, int z1);
float VoxelLighting_Sample(float x, float y, float z);
/* Rays cast so far (samples not found in the cache), for the build logs. */
unsigned VoxelLighting_Rays(void);
/* The light a face gets from the sun for its facing alone, VOXEL_AMBIENT for
 * a face turned away. The normal need not be unit length. */
float VoxelLighting_Face(float nx, float ny, float nz);
void VoxelLighting_Quad(VoxelBuilder *builder, const VoxelVertex *a,
                         const VoxelVertex *b, const VoxelVertex *c,
                         const VoxelVertex *d);
/*
 * A modelled building's triangle. `drawnShade` is the face shade the model
 * was written with (voxel_building.py's SHADE_*): the side the face was drawn
 * for, since models are not wound consistently. It is replaced by the
 * sun's facing; models take no cast shadow.
 */
void VoxelLighting_ModelTri(VoxelBuilder *builder, const VoxelVertex *a,
                            const VoxelVertex *b, const VoxelVertex *c, float drawnShade);
void VoxelLighting_Contact(VoxelBuilder *builder, float x, float z);
#endif

#endif
