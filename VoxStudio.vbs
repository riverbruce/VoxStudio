' VoxStudio launcher: mo app khong hien cua so den (console).
Option Explicit
Dim fso, sh, dir, pyw, env
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")
dir = fso.GetParentFolderName(WScript.ScriptFullName)
pyw = dir & "\.venv\Scripts\pythonw.exe"
If Not fso.FileExists(pyw) Then
  MsgBox "VoxStudio chua cai dat xong." & vbCrLf & "Hay chay file install.bat trong thu muc:" & vbCrLf & dir, vbExclamation, "VoxStudio"
  WScript.Quit 1
End If
Set env = sh.Environment("Process")
env("HF_HOME") = dir & "\cache\hf"
env("MODELSCOPE_CACHE") = dir & "\cache\modelscope"
env("PYTHONIOENCODING") = "utf-8"
env("PYTHONUTF8") = "1"
env("HF_HUB_OFFLINE") = "1"
sh.CurrentDirectory = dir
sh.Run """" & pyw & """ """ & dir & "\main.py""", 0, False
