-- Get the path to the app bundle
set appPath to POSIX path of (path to me)

-- Strip trailing slash safely just in case, though cd works either way
-- The shell command CD's into the app bundle, then up one level to the project root
-- We run Python SYNCHRONOUSLY by not appending an ampersand (&).
-- This keeps the applet alive, preventing LaunchServices from killing the process group!

set shellCommand to "cd " & quoted form of appPath & " && cd .. && venv/bin/SystemManagementService -u syssvc.py >> .launcher.log 2>&1"

do shell script shellCommand
