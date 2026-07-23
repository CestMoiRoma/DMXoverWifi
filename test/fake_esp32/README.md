# Fake ESP32

Stand-ins for the CircuitPython modules the firmware imports. Putting this
directory on `sys.path` makes `import board`, `import wifi`, `import busio` and
friends resolve here instead of failing, so `src/` can be imported and exercised
by a normal desktop Python.

These are not emulators. They record what the firmware did to them and let a test
assert on it, or feed values back in. Every stub exposes plain attributes and
lists for that purpose, documented in each file.

Real standard-library modules are deliberately **not** stubbed. `os`, `json`,
`time`, `gc` and `ipaddress` all exist on CPython with the API the firmware uses.

When the firmware starts importing something new, add a stub here. Keep it as thin
as the firmware needs and no thinner: a stub that accepts calls the real hardware
would reject makes the suite lie.
