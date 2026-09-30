import pathlib

lines = pathlib.Path("/home/yoke/Downloads/littleprince-launcher/lpo/server.py").read_text().splitlines()
start = next(i for i, l in enumerate(lines) if l.startswith("def dispatch_service"))
for i in range(start, start + 105):
    l = lines[i]
    if not l.strip():
        continue
    indent = len(l) - len(l.lstrip())
    tag = "   <<<" if l.strip().startswith(("def ", "if ", "return ", "CLIENT_RANK")) else ""
    print("%5d [%d] %s%s" % (i + 1, indent, l[:78], tag))
