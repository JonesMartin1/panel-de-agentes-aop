import argparse
from pathlib import Path

import numpy as np
import trimesh
from PIL import Image
from scipy.ndimage import distance_transform_edt


def prepare(path: Path):
    rgba = np.asarray(Image.open(path).convert("RGBA")).copy()
    rgb = rgba[:, :, :3].astype(np.int16)
    neutral_white = ((rgb.max(2) - rgb.min(2)) < 16) & (rgb.mean(2) > 220)
    opaque = (rgba[:, :, 3] > 24) & ~neutral_white
    if not opaque.any():
        raise ValueError(f"No se detectó figura opaca en {path}")
    nearest = distance_transform_edt(~opaque, return_distances=False, return_indices=True)
    filled = rgba[:, :, :3][tuple(nearest)]
    ys, xs = np.where(opaque)
    return filled, (xs.min(), ys.min(), xs.max(), ys.max())


def sample(prepared, name, u, v):
    pixels, (x0, y0, x1, y1) = prepared[name]
    x = np.rint(x0 + np.clip(u, 0, 1) * (x1 - x0)).astype(int)
    y = np.rint(y0 + np.clip(v, 0, 1) * (y1 - y0)).astype(int)
    return pixels[y, x].astype(np.float32)


def main():
    parser = argparse.ArgumentParser(description="Proyecta cuatro vistas como colores de vértice en un GLB.")
    parser.add_argument("--model", required=True, type=Path)
    for name in ("front", "back", "left", "right"):
        parser.add_argument(f"--{name}", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--side-threshold", type=float, default=1.35)
    parser.add_argument("--front-axis", choices=("positive-z", "negative-z"), default="positive-z")
    args = parser.parse_args()

    views = {name: getattr(args, name) for name in ("front", "back", "left", "right")}
    prepared = {name: prepare(path) for name, path in views.items()}
    scene = trimesh.load(args.model, force="scene")
    if not scene.geometry:
        raise ValueError(f"El archivo no contiene mallas: {args.model}")
    mesh = trimesh.util.concatenate(tuple(scene.geometry.values()))
    vertices, normals = mesh.vertices, mesh.vertex_normals
    mins, maxs = mesh.bounds
    span = np.maximum(maxs - mins, 1e-9)
    ux = (vertices[:, 0] - mins[0]) / span[0]
    vy = (maxs[1] - vertices[:, 1]) / span[1]
    uz = (vertices[:, 2] - mins[2]) / span[2]
    samples = np.stack((
        sample(prepared, "front", ux, vy),
        sample(prepared, "back", 1.0 - ux, vy),
        sample(prepared, "left", 1.0 - uz, vy),
        sample(prepared, "right", uz, vy),
    ), axis=1)

    nx, nz = normals[:, 0], normals[:, 2]
    if args.front_axis == "negative-z":
        nz = -nz
    weights = np.zeros((len(vertices), 4), dtype=np.float32)
    side = np.abs(nx) > np.abs(nz) * args.side_threshold
    weights[~side & (nz >= 0), 0] = 1
    weights[~side & (nz < 0), 1] = 1
    weights[side & (nx < 0), 2] = 1
    weights[side & (nx >= 0), 3] = 1
    rgb = np.clip((samples * weights[:, :, None]).sum(1), 0, 255).astype(np.uint8)
    rgba = np.column_stack((rgb, np.full(len(rgb), 255, dtype=np.uint8)))
    mesh.visual = trimesh.visual.ColorVisuals(mesh=mesh, vertex_colors=rgba)
    mesh.visual.material = trimesh.visual.material.PBRMaterial(
        name="Four-view projected colors", baseColorFactor=[255, 255, 255, 255],
        metallicFactor=0.04, roughnessFactor=0.7,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    mesh.export(args.output, file_type="glb")
    print(args.output)
    print(f"vertices={len(mesh.vertices)} faces={len(mesh.faces)}")


if __name__ == "__main__":
    main()
