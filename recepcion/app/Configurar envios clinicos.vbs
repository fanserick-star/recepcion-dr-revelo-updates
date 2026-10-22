Option Explicit
Dim shell, fso, folder, pyw, script
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
folder = fso.GetParentFolderName(WScript.ScriptFullName)
pyw = fso.BuildPath(folder, ".venv\Scripts\pythonw.exe")
script = fso.BuildPath(folder, "clinical_delivery_setup.pyw")
If Not fso.FileExists(pyw) Then
  MsgBox "No se encontró Python de Recepción. Abre primero el programa usando el launcher y vuelve a intentar.", 48, "Dr. Revelo"
ElseIf Not fso.FileExists(script) Then
  MsgBox "No se encontró el asistente. Actualiza Recepción.", 48, "Dr. Revelo"
Else
  shell.Run Chr(34) & pyw & Chr(34) & " " & Chr(34) & script & Chr(34), 1, False
End If
