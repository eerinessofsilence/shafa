Set shell = CreateObject("WScript.Shell")

If WScript.Arguments.Count = 0 Then
  WScript.Quit 1
End If

command = WScript.Arguments(0)
shell.Run command, 0, False
