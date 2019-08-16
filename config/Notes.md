# Notes
## Parameters live-refresh
Most parameters are live-refreshed. You do not need to restart the program after making changes. There still are parameters that are not immediatly refreshed:
- The port and the address of HTTP servers are never reloaded.
- New serial port and baudrate are not used until a new serial connection is attempted by the program. This occurs after a failed connection attempt or when a problem is detected.
