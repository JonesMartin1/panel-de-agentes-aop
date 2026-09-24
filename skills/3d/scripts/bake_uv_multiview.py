import argparse
from pathlib import Path

import cv2
import numpy as np
import trimesh
import xatlas
from PIL import Image
from scipy.ndimage import distance_transform_edt


def prepare(path):
    rgba = np.asarray(Image.open(path).convert("RGBA"))
    rgb = rgba[:, :, :3].astype(np.int16)
    white = ((rgb.max(2) - rgb.min(2)) < 16) & (rgb.mean(2) > 220)
    mask = (rgba[:, :, 3] > 24) & ~white
    nearest = distance_transform_edt(~mask, return_distances=False, return_indices=True)
    filled = rgba[:, :, :3][tuple(nearest)].astype(np.float32)
    ys, xs = np.where(mask)
    return filled, (xs.min(), ys.min(), xs.max(), ys.max())


def sample(view, u, v):
    pixels, (x0, y0, x1, y1) = view
    x = x0 + np.clip(u, 0, 1) * (x1 - x0)
    y = y0 + np.clip(v, 0, 1) * (y1 - y0)
    map_x = x.astype(np.float32).reshape(-1, 1)
    map_y = y.astype(np.float32).reshape(-1, 1)
    return cv2.remap(pixels, map_x, map_y, cv2.INTER_CUBIC,
                     borderMode=cv2.BORDER_REPLICATE).reshape(-1, 3)


def projected_colors(points, normals, bounds, views, threshold):
    mins, maxs = bounds
    span = np.maximum(maxs - mins, 1e-9)
    ux = (points[:, 0] - mins[0]) / span[0]
    vy = (maxs[1] - points[:, 1]) / span[1]
    uz = (points[:, 2] - mins[2]) / span[2]
    nx, nz = normals[:, 0], normals[:, 2]
    side = np.abs(nx) > np.abs(nz) * threshold
    result = np.empty((len(points), 3), dtype=np.float32)
    selectors = (
        (~side & (nz >= 0), "front", ux),
        (~side & (nz < 0), "back", 1 - ux),
        (side & (nx < 0), "left", 1 - uz),
        (side & (nx >= 0), "right", uz),
    )
    for choose, name, horizontal in selectors:
        if choose.any():
            result[choose] = sample(views[name], horizontal[choose], vy[choose])
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, type=Path)
    for name in ("front", "back", "left", "right"):
        ap.add_argument(f"--{name}", required=True, type=Path)
    ap.add_argument("--output", required=True, type=Path)
    ap.add_argument("--texture", type=int, default=2048)
    ap.add_argument("--side-threshold", type=float, default=1.35)
    args = ap.parse_args()

    source = trimesh.load(args.model, force="scene")
    mesh = trimesh.util.concatenate(tuple(source.geometry.values()))
    vertices = np.asarray(mesh.vertices, dtype=np.float32)
    faces = np.asarray(mesh.faces, dtype=np.uint32)
    normals = np.asarray(mesh.vertex_normals, dtype=np.float32)
    views = {n: prepare(getattr(args, n)) for n in ("front", "back", "left", "right")}

    vmapping, atlas_faces, uvs = xatlas.parametrize(vertices, faces)
    out_vertices = vertices[vmapping]
    out_normals = normals[vmapping]
    size = args.texture
    texture = np.zeros((size, size, 3), dtype=np.uint8)
    occupied = np.zeros((size, size), dtype=np.uint8)
    uv_px = uvs * (size - 1)
    uv_px[:, 1] = (1 - uvs[:, 1]) * (size - 1)

    for face_index, tri in enumerate(atlas_faces):
        pts = uv_px[tri]
        x0, y0 = np.maximum(np.floor(pts.min(0)).astype(int), 0)
        x1, y1 = np.minimum(np.ceil(pts.max(0)).astype(int), size - 1)
        if x1 < x0 or y1 < y0:
            continue
        xs, ys = np.meshgrid(np.arange(x0, x1 + 1), np.arange(y0, y1 + 1))
        p = np.column_stack((xs.ravel() + .5, ys.ravel() + .5))
        a, b, c = pts
        den = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
        if abs(den) < 1e-8:
            continue
        w0 = ((b[1] - c[1]) * (p[:, 0] - c[0]) + (c[0] - b[0]) * (p[:, 1] - c[1])) / den
        w1 = ((c[1] - a[1]) * (p[:, 0] - c[0]) + (a[0] - c[0]) * (p[:, 1] - c[1])) / den
        w2 = 1 - w0 - w1
        inside = (w0 >= -.001) & (w1 >= -.001) & (w2 >= -.001)
        if not inside.any():
            continue
        bary = np.column_stack((w0[inside], w1[inside], w2[inside]))
        original_tri = faces[face_index]
        world = bary @ vertices[original_tri]
        normal = bary @ normals[original_tri]
        normal /= np.maximum(np.linalg.norm(normal, axis=1, keepdims=True), 1e-9)
        colors = projected_colors(world, normal, mesh.bounds, views, args.side_threshold)
        px, py = p[inside].astype(int).T
        texture[py, px] = np.clip(colors, 0, 255).astype(np.uint8)
        occupied[py, px] = 1

    indices = distance_transform_edt(occupied == 0, return_distances=False, return_indices=True)
    texture = texture[tuple(indices)]
    image = Image.fromarray(texture, "RGB")
    material = trimesh.visual.material.PBRMaterial(
        name="UV multiview 2K", baseColorTexture=image,
        metallicFactor=0.04, roughnessFactor=0.62,
    )
    output_mesh = trimesh.Trimesh(vertices=out_vertices, faces=atlas_faces, process=False)
    output_mesh.visual = trimesh.visual.TextureVisuals(uv=uvs, image=image, material=material)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    output_mesh.export(args.output, file_type="glb")
    image.save(args.output.with_suffix(".png"), optimize=True)
    print(args.output)
    print(f"vertices={len(out_vertices)} faces={len(atlas_faces)} texture={size}")


if __name__ == "__main__":
    main()
