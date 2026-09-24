# Textura nativa de Hunyuan en Windows (RTX 4070 Laptop, 8 GB)

Esta receta quedó comprobada al texturizar una taza de espresso. Usarla únicamente cuando el usuario pide una textura nativa y acepta el consumo; para un flujo normal de 8 GB siguen siendo preferibles los horneados multivista de la skill principal.

> Las rutas son las de la instalación original (`D:\IA\modelos-3d`). Reemplazarlas por las reales.

## Estado que funcionó

- Código: `D:\IA\modelos-3d\Hunyuan3D-2`
- Entorno: `D:\IA\modelos-3d\Hunyuan3D-2\conda-env`
- GPU: RTX 4070 Laptop de 8 GB; CUDA Toolkit 12.4; Python 3.11.
- Paquetes compatibles: `torch==2.5.1+cu124`, `torchvision==0.20.1+cu124`, `transformers==4.48.0`, `diffusers==0.32.2`, `huggingface-hub==0.27.1`, `numpy==1.26.4`.
- El resultado de prueba fue un GLB texturizado de 3,6 MB desde una copia web de unas 30 mil caras, con pico de VRAM asignada de ~7,15 GB.

No actualizar esos paquetes por rutina: las versiones recientes de PyTorch, Transformers, Diffusers y NumPy rompen distintas partes del código de Hunyuan en Windows. Antes de modificar el entorno, confirmar autorización del usuario porque puede descargar varios GB y afectar otros visores de Hunyuan.

## Requisito de compilación (una vez por entorno)

Hunyuan Paint necesita dos extensiones locales. Requiere Visual Studio Build Tools 2022 con C++ y `vcvars64.bat`; no alcanza con tener `nvcc`.

Abrir el entorno MSVC y fijar estas variables antes de cada instalación:

```bat
call "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat"
set SETUPTOOLS_USE_DISTUTILS=stdlib
set DISTUTILS_USE_SDK=1
```

Después, desde el intérprete del entorno de Hunyuan, instalar ambos componentes:

```bat
cd /d D:\IA\modelos-3d\Hunyuan3D-2\hy3dgen\texgen\custom_rasterizer
python setup.py install
cd /d D:\IA\modelos-3d\Hunyuan3D-2\hy3dgen\texgen\differentiable_renderer
python setup.py install
```

Validar antes de ocupar GPU:

```bat
python -c "import torch, custom_rasterizer, custom_rasterizer_kernel, mesh_processor; print(torch.__version__)"
```

La combinación `torch` cu124 y CUDA 12.4 evitó la incompatibilidad que aparecía con PyTorch cu128. Si aparece `vcvarsall.bat` o falta `cl.exe`, falta Build Tools; si aparece `DISTUTILS_USE_SDK`, esa variable no quedó aplicada.

## Compatibilidad del código local

Con Diffusers 0.32.2, el cargador del pipeline local de Hunyuan puede requerir permiso explícito para su pipeline propio. En `hy3dgen/texgen/utils/multiview_utils.py`, la llamada a `DiffusionPipeline.from_pretrained` debe incluir `trust_remote_code=True` junto a `custom_pipeline=...`.

Hacer este ajuste sólo en la copia local conocida de Hunyuan. Los pesos usados deben ser los ya descargados y revisados de `tencent/Hunyuan3D-2`; no habilitar código remoto de un repositorio desconocido.

## Ejecución segura

1. Conservar el maestro y producir una copia web primero (aprox. 30 mil caras fue viable). No empezar con el maestro de alta densidad: su horneado 2K puede tardar muchísimo y no llegar a exportar en una laptop de 8 GB.
2. Cargar la referencia RGBA y eliminar fondo sólo si corresponde.
3. Usar `Hunyuan3DPaintPipeline.from_pretrained(..., subfolder='hunyuan3d-paint-v2-0-turbo')` y llamar `enable_model_cpu_offload()`.
4. Exportar con otro nombre, por ejemplo `objeto-textured-web.glb`; nunca sobrescribir la malla aprobada.
5. Vigilar `nvidia-smi`. La corrida comprobada ocupó entre ~6,6 y 7,3 GB; detener si alcanza el límite o si el sistema empieza a paginar.
6. No asumir que "terminó" hasta verificar que el GLB existe, abre y muestra frente y perfil.

## Lectura del resultado e integración web

- La textura nativa puede resolver silueta y volumen mejor que el color por vértice, pero también puede inventar cerámica, adornos o colores aunque la referencia pida vidrio. No activar el asset por el mero hecho de que exportó.
- Si la geometría es buena y el material no respeta la referencia, conservar la geometría y sustituir el material en la escena web por el material solicitado (por ejemplo, vidrio claro), manteniendo el líquido como malla independiente.
- Al ubicar un recipiente bajo otro modelo, normalizar su bounding box por el mínimo vertical. Aun así cada variante puede tener piso local distinto: medir el punto más bajo del vaso y del platillo, compensarlo contra una única cota de bandeja y verificar cada receta por separado.
- En escenas Three.js con animación continua, la captura de Playwright puede quedar esperando. Tras cargar la bebida, congelar el próximo `requestAnimationFrame` y capturar cada receta por separado; revisar escritorio, móvil y consola.

## Licencia

El repositorio de Hunyuan indica licencia no comercial. Antes de publicar o usar comercialmente cualquier salida del modelo, comprobar la licencia vigente de Hunyuan y de la imagen fuente.
