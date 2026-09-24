# UniRig local: personaje animable

Usar este flujo únicamente cuando el modelo aprobado sea humanoide y el usuario pida animación corporal, rig o mayor configurabilidad. Para objetos y criaturas no humanoides, evaluar otra solución.

> Las rutas son las de la instalación original (`D:\IA\modelos-3d`). Reemplazarlas por las reales.

## Instalación conocida

- Windows aloja todo lo pesado en `D:\IA\modelos-3d\UniRig`.
- La ejecución se hace dentro de Ubuntu por WSL; no instalar el entorno en el repo del sitio.
- Entorno Python: `D:\IA\modelos-3d\UniRig\.venv`.
- Caché de Hugging Face: `D:\IA\modelos-3d\UniRig\hf-cache`.
- Caché de uv: `D:\IA\modelos-3d\UniRig\.uv-cache`.
- Python local de uv: `D:\IA\modelos-3d\UniRig\.uv-python`.
- Combinación comprobada: Python 3.11, PyTorch 2.4.1 CUDA 12.4, `flash-attn` 2.8.3, `spconv-cu124`, `torch-scatter`, `torch-cluster`, Blender Python (`bpy`) 4.2.

La RTX 4070 Laptop de 8 GB completó esqueleto y skinning sin OOM. La inferencia del esqueleto usó alrededor de 4.6 GB de VRAM. No iniciar en paralelo Hunyuan, Ollama, Whisper u otros consumidores importantes de GPU.

## Flujo probado

1. Partir del GLB maestro texturado ya aprobado. Conservarlo intacto.
2. Ejecutar primero la inferencia de esqueleto de UniRig y después skinning. Los scripts oficiales están en `launch/inference`; si WSL acusa `$'\r'`, normalizar CRLF sólo en esos scripts.
3. Unir geometría, armature y pesos en una copia GLB. Quitar objetos auxiliares de inspección y limpiar toda pose de prueba antes de exportar.
4. Renderizar al menos una imagen en reposo y otra con cabeza, pecho y ambos brazos rotados. Comprobar silueta, hombros, codos, manos y estabilidad de las piernas.
5. Conservar el rig maestro. Para web, comprimir una copia con glTF Transform Meshopt en nivel medio. No usar decimación agresiva: en el caso probado redujo peso pero dañó visiblemente la textura.
6. Inspeccionar que la copia conserve `JOINTS_0` y `WEIGHTS_0`. Probarla en el navegador, porque la inspección del archivo sola no garantiza que el skin siga activo.

## Integración Three.js

- Configurar `GLTFLoader.setMeshoptDecoder(MeshoptDecoder)` cuando la copia use `EXT_meshopt_compression`.
- Recorrer los huesos por nombre y armar un mapa semántico después de inspeccionar el armature; no suponer nombres Mixamo.
- Para una interacción corta se pueden rotar huesos directamente y volver suavemente a la pose base. Para varias acciones reutilizables, guardar clips y usar `AnimationMixer`.
- Mantener flotación y seguimiento suave como capas independientes. Respetar `prefers-reduced-motion` y conservar el fallback 2D.

## Referencia comprobada

En la instalación original, un personaje EVA quedó con rig de 37 huesos, maestro limpio y copia web Meshopt (`UniRig\results\eva`). Esa referencia sirve para repetir el procedimiento, no para sobrescribir esos archivos.
