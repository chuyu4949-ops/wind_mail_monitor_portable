Set shell = CreateObject("WScript.Shell")
Set files = CreateObject("Scripting.FileSystemObject")
base = shell.ExpandEnvironmentStrings("%LOCALAPPDATA%\WindMailMonitor\AutoPush")
worker = base & "\github_auto_push_loop.cmd"
If files.FileExists(worker) Then
    shell.Run "cmd.exe /d /c """ & worker & """", 0, False
End If
