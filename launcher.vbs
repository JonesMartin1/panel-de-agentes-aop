' Acceso "Servidor IA": lanza el panel oculto, PRENDE todos los servicios
' (incluida la voz) y abre el navegador. Cuando el asistente esta listo,
' avisa por voz: "Listo, te escucho".
Set sh = CreateObject("WScript.Shell")
' 0 = ventana oculta ; False = no esperar
' --auto: si el panel arranca de cero, prende todo solo
sh.Run """D:\IA\envs\wpp\python.exe"" ""D:\IA\wpp-transcriptor\panel.py"" --auto", 0, False
WScript.Sleep 3500
' Si el panel YA estaba corriendo (el python de arriba muere por puerto ocupado),
' estos POST prenden los servicios igual; si ya estan prendidos, no hacen nada.
sh.Run "powershell -WindowStyle Hidden -Command ""try{irm -Method Post http://localhost:8750/start -TimeoutSec 10}catch{}; try{irm -Method Post http://localhost:8750/start/voz -TimeoutSec 10}catch{}""", 0, False
' Abrir el panel en su ventana propia (app de escritorio, ver app/escritorio.py).
' pythonw = sin ventana de consola; CurrentDirectory tiene que ser la raiz del
' proyecto, si no Python no encuentra el paquete `app` y el -m falla.
' Si preferis el navegador de siempre: sh.Run "http://localhost:8750", 1, False
sh.CurrentDirectory = "D:\IA\wpp-transcriptor"
sh.Run """D:\IA\envs\wpp\pythonw.exe"" -m app.escritorio", 0, False
