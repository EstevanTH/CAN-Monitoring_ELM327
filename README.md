# CAN Monitoring (ELM327)
This program reads CAN frames from an ELM327 / ELM329 chip (widely available) and makes them available through:
- a WebSocket server (JSON format),
- a CAN-ETH output (that is CAN over UDP),
- a Wireshark-compatible libpcap file.

## Features
- A simplistic Web interface showing the last frame for each identifier  
    ![Web interface preview](https://cdn.discordapp.com/attachments/611966770135433216/611967744803340289/unknown.png)
- Customizable "sequence", which is the startup configuration (overridable on the Web interface)
- Automatic recover from most possible communication errors
- Allows any supported serial port baudrate (`AT BRD` command)
- Configuration is live-refreshed (no restart needed)
- Multiple instances allowed using different parameters files (allowing different CAN buses simultaneously)
- Possibility to run multiple HTTP servers for better performance
- Nice console output to easily debug problems
- Optional libpcap SocketCAN logging of received CAN frames

## Requirements
- An OBD scanner featuring an ELM327 / ELM329 chip (preferably connected through bare RS-232 or USB converter)
- [Python 3.6 or greater, extended to Python 3.4.4](https://www.python.org/downloads/)
- [pySerial 3.0.1 or greater](https://github.com/pyserial/pyserial)
- An OS supported by pySerial

## Instructions
1. Install *Python3*.
1. Install *pySerial*.
1. Edit the files `parameters.py` and `sequenceELM327_CAN.py` in the sub-directory `config`.
1. When you are ready to start, run `main.py`.

# Extra information
- The default web interface is available at `http://127.0.0.1:18327/show_dataframes.htm`
- Command line arguments:
    - `"--parameters=<file>"` Override the parameters file (relative to `config` or absolute).
    - `"--sequence=<file>"` Override the sequence file (relative to `config` or absolute).

# Known problems
- I receive `BUFFER FULL` alerts frequently!
    - You should try to increase the serial port baudrate.
    - If it is not enough, try to play with the hardware CAN filter (or the CAN whitelist that will set it up automatically) to reduce the amount of data.
- I receive invalid CAN frames and empty lines randomly!
    - *pySerial* seems to produce a huge CPU usage on *Windows*. When the receive buffer of the serial port overflows, some data gets flushed and to the program the lost bytes have never existed: at this point the line of data is like the beginning of a frame and the end of another. So most often this produces an invalid CAN frame representation, but sometimes a weird valid frame that never existed shows up.
    - You can try to reduce the amount of data (solution below).
    - You can increase the process priority in the task manager.
    - Note that under such conditions, CAN frames are lost and the latency of CAN readings is increased.

## Support
You can open an issue when you have a question, or you can join my Discord server [Yvon à bord !](https://discord.gg/pDasWGC) where you are very welcome, or see my contact details on my GitHub profile.
