# TuwaiqOS validation checklist

Run `.\scripts\run-qemu.ps1` and verify:

```text
help
ls
touch hello.txt
write hello.txt hello
cat hello.txt
reboot
cat hello.txt
ps
sysinfo
notes create todo
notes list
monitor
run hello
```

Expected boot screen:

```text
TuwaiqOS v0.5
AI-Native Experimental Operating System

tuwaiq@os:~$
```
