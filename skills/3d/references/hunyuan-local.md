# Hunyuan local

> Estas son las rutas y valores de la instalación original (Windows, RTX 4070 Laptop de 8 GB,
> todo en `D:\IA\modelos-3d`). En otra máquina, reemplazarlos por los reales antes de usar
> cualquier comando: las rutas del panel (`app/rutas.py`, `DIR_3D`) tienen que coincidir.

## Instalación conocida

- Código: `D:\IA\modelos-3d\Hunyuan3D-2`
- Entorno: `D:\IA\modelos-3d\Hunyuan3D-2\conda-env`
- Caché de Hugging Face: `D:\IA\modelos-3d\hunyuan-cache`
- Pesos locales: `D:\IA\modelos-3d\hunyuan-models`
- Caché de salidas Gradio: `D:\IA\modelos-3d\hunyuan-gradio-cache`
- Caché de remoción de fondo: `D:\IA\modelos-3d\rembg-cache`
- Interfaz: puerto `7860`
- Modelo liviano: `tencent/Hunyuan3D-2mini`, subcarpeta `hunyuan3d-dit-v2-mini-turbo`
- Modelo multivista: `tencent/Hunyuan3D-2mv`, subcarpeta `hunyuan3d-dit-v2-mv-turbo`

## Modo exclusivo de GPU

Al generar 3D, Hunyuan tiene que ser el único modelo de cómputo encendido. El modo exclusivo es una sesión temporal y debe conservar una foto del estado anterior para poder restaurarlo. Antes de arrancarlo:

1. Consultar `http://127.0.0.1:8750/placa` y `http://127.0.0.1:8750/status`. Guardar en la carpeta de trabajo qué modelos y servicios estaban vivos antes de tocar la GPU. El panel ya distingue procesos de cómputo `C` de procesos gráficos `C+G` mediante `nvidia-smi pmon`.
2. Apagar cada entrada de `procesos` mediante `POST /placa/apagar/<pid>`. Si corresponde a Voz de Laura, Telegram o WhatsApp, el panel la apaga como servicio y registra que fue intencional. No matar todos los `python.exe` ni buscar por una palabra genérica.
3. Apagar cualquier entrada de `modelos` distinta de Hunyuan que esté `vivo` o `cargando`, mediante `POST /placa/modelo/<clave>/apagar`. Ollama puede estar servido sin tener un modelo en VRAM; para este modo exclusivo se apaga igualmente.
4. Dejar intactos los procesos `C+G` del escritorio. Antivirus, Explorer, navegador y utilidades gráficas no son modelos.
5. Verificar de nuevo `/placa`: `procesos` debe quedar vacío, Ollama apagado y Hunyuan vivo. Confirmar además HTTP 200 en `http://127.0.0.1:7860` y que el único proceso tipo `C` en `nvidia-smi pmon -c 1` sea Hunyuan.

No usar PIDs guardados para operar: cambian en cada arranque. La foto previa sólo registra nombres y estados; cada acción usa una foto fresca del panel.

## Cierre de la sesión exclusiva

Cuando termina el último trabajo que necesita Hunyuan:

1. Apagarlo mediante `POST /placa/modelo/hunyuan/apagar`. No dar por terminado el trabajo mientras siga `vivo` o `cargando`.
2. Esperar a que el puerto 7860 cierre y comprobar que la memoria GPU baje.
3. Restaurar únicamente lo que la foto previa marcaba como encendido y que fue detenido para liberar la GPU. Los servicios del panel vuelven con `POST /start/<servicio>`; los modelos administrados, con `POST /placa/modelo/<clave>/prender`.
4. No encender Ollama ni ningún otro modelo que ya estuviera apagado antes de la sesión.
5. Verificar el estado final: Hunyuan apagado, los servicios y modelos previos nuevamente vivos y ningún proceso inesperado en la lista de cómputo.

Si el trabajo continúa en otro turno o el usuario pide mantener Hunyuan listo, no cerrar todavía. En cualquier otro caso, el cierre forma parte del criterio de terminado y no se deja para que el usuario lo haga manualmente.

## Arranque reproducible

Definir estos valores antes de iniciar el proceso:

```powershell
$hyRoot = 'D:\IA\modelos-3d\Hunyuan3D-2'
$env:HF_HOME = 'D:\IA\modelos-3d\hunyuan-cache'
$env:HY3DGEN_MODELS = 'D:\IA\modelos-3d\hunyuan-models'
$env:U2NET_HOME = 'D:\IA\modelos-3d\rembg-cache'
```

El primer resultado aprobado (2026-08-25) se generó con el servidor en su variante predeterminada `2mini`, sin argumentos de modelo explícitos:

```powershell
Start-Process -FilePath "$hyRoot\conda-env\python.exe" `
  -ArgumentList @(
    "$hyRoot\gradio_app.py",
    '--port','7860','--host','0.0.0.0',
    '--disable_tex','--enable_flashvdm','--low_vram_mode',
    '--cache-path','D:\IA\modelos-3d\hunyuan-gradio-cache'
  ) `
  -WorkingDirectory $hyRoot -WindowStyle Hidden
```

Para multivista real, agregar de forma explícita:

```text
--model_path tencent/Hunyuan3D-2mv
--subfolder hunyuan3d-dit-v2-mv-turbo
```

No inferir la variante por el nombre del archivo de salida ni por los argumentos que manda el cliente. `gradio_app.py` usa `2mini` por defecto y, en ese modo, ignora `mv_image_back`, `mv_image_left` y `mv_image_right`. Registrar el valor real de `stats.model.shapegen` devuelto por Gradio. Si se necesita 2mv y el puerto 7860 ya está ocupado, inspeccionar la línea de comando o el título de la página; apagar esa instancia y arrancar la variante correcta.

## Ajuste comprobado para RTX 4070 Laptop de 8 GB

Iniciar con `--disable_tex --low_vram_mode`. Usar como base:

- resolución octree: 256
- pasos: 5
- guidance: 5
- chunks: 8000
- seed: entre 0 y 10000000

Esta combinación generó una malla de aproximadamente 128 mil caras sin OOM. No asumir que Hunyuan3D 2.5 ni el texturizador nativo caben. La textura nativa ronda un requisito práctico de 16 GB; en 8 GB usar color proyectado o detenerse si el usuario exige textura nativa.

El caso aprobado usó `2mini`, frente único, semilla `240825`, 5 pasos, guidance 5, octree 256 y chunks 8000. Produjo 126.004 vértices y 252.004 triángulos. Las cuatro láminas se conservaron como referencia visual, pero las vistas extra no participaron de esa generación.

## Diagnóstico

- Si la figura es incorrecta pero no hubo OOM, mejorar primero la coherencia de las cuatro vistas.
- Si aparece OOM, no insistir con parámetros mayores: liberar sólo procesos autorizados, bajar resolución/chunks o proponer una alternativa más liviana.
- No mezclar instalaciones pesadas con el repositorio del destino.
- Si un resultado supuestamente multivista se obtuvo con una instancia `2mini`, corregir el manifiesto y no presentarlo como 2mv. Para comparar variantes, conservar la salida anterior y generar una copia nueva con los argumentos explícitos.
