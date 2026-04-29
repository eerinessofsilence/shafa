Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
batPath = fso.BuildPath(scriptDir, "start-windows-dev.bat")
projectRoot = fso.GetAbsolutePathName(fso.BuildPath(scriptDir, ".."))

shell.CurrentDirectory = projectRoot
shell.Run """" & batPath & """", 0, False
