### HTTP servers ###
#~ What IP address and TCP port do you need to bind each server to?
#~ For how many seconds should unrefreshed data remain valid? 0.0 means that data never expire. After the delay, the server returns the HTTP status 504 Gateway Time-out.
httpBindings = [
	{"address": "127.0.0.1", "port": 18327},
	{"address": "0.0.0.0", "port": 18327},
]

### Serial port ###
#~ Which serial port to choose?
serialPort = "COM9"
#~ What is the baud rate used by the ELM327 by default?
serialBaudRateInitial = 38400
#~ What baud rate would you like to use instead? It can be the same as serialBaudRateInitial if you need no change. Tip: a change is good to detect resets!
serialBaudRateDesired = 230400
#~ Should the initialization restart when the desired baud rate could not be set?
serialBaudRateDesiredForce = True
#~ Should serial read operations use a local buffer? This can help save CPU power at high baud rates and thus avoid lost bytes.
serialLocalBufferEnabled = True
#~ If serialLocalBufferEnabled, should ATMA result be accumulated? (adds delay but saves CPU power with high serial port flow - should be disabled with small serial flow / baudrate)
serialLocalBufferAccuATMA = True
#~ If serialLocalBufferAccuATMA, how many bytes to read at minimum during ATMA? Default: 64 - Minimum: 1
serialLocalBufferMinFillATMA = 64
#~ If serialLocalBufferAccuATMA, how many seconds to wait during each read operation during ATMA? Default: 0.002
serialLocalBufferWaitTimeATMA = 0.002
#~ For debuggers: show everything that is sent to the ELM327?
# serialShowSentBytes = False
serialShowSentBytes = True
#~ For debuggers: show everything that is received from the ELM327? (bad idea: huge flow making malfunction caused by slowdown)
serialShowReceivedBytes = False

### CAN bus ###
#~ Check if found buses are OBD-compliant? (No connectivity test otherwise)
canBusTestObdCompliant = False
#~ Which CAN bus specification should be used? 0 is for auto-detection, others are described in the ELM327 manual. Auto-detection is only for OBD-compliant CAN buses.
ATSP = b'B'
#~ Allow decoding frames with a 29-bit identifier on an 11-bit CAN bus and vice-versa? Expect parasitic frames when "BUFFER FULL".
canBusAllowMixedIdentifiers = True
#~ How many seconds to wait while scanning values from the sequence? Should be short (for config live-refresh) but reasonable (delay between frames). Should also be fast to quickly leave a buggy silent ATMA call. Adjustable with the API. Must be greater than 0.
canBusInactivityTimeout = 0.3
#~ How long to wait before considering an ATMA interruption attempt expired?
canBusStopMonitoringWait = 1.5
#~ After that number of ATMA interruption attempts, resets the communication to exit from a stuck ATMA reading state.
canBusStopMonitoringMaxAttempts = 10
#~ If ATMA seems to return more than this number of invalid frames in a row then monitoring is interrupted. Under heavy CPU load the buffer gets randomly flushed so corrupted frames may be read.
canBusMaxStraightInvalidFrames = 20
#~ When setting ATCF & ATCM, mask chosen bits unconditionnally. Should be None except for buggy firmwares (Icar01 ELM327 V1.5 needs 0x1F00FFFF).
canBusMaskOver = None
#~ USER1 protocol: which is the common identifier length? 11-bit = True, 29-bit = False
ATPB_11bit = False
#~ USER1 protocol: can data frame have less than 8 data bytes?
ATPB_variableDataLength = False
#~ USER1 protocol: how are frames formatted? Choices are "ISO 15765-4", "SAE J1939", None.
ATPB_dataFormat = None
ATPB_rate = 500.

### Libpcap & CAN-ETH outputs ###
#~ Log CAN frames to a libpcap file (Wireshark-compatible)? Enter a filename or None.
from datetime import datetime
pcapOutputFile = "logs/CAN "+datetime.now().strftime( "%Y-%m-%d %H-%M-%S" )+" "+serialPort.replace( "/",";" )+".pcap"
#~ Send CAN frames on the network?
canEthUdpEnabled = True
canEthUdpIpVersion = 4
canEthUdpAddrSrc = "192.168.56.1"
canEthUdpPortSrc = 11898
canEthUdpAddrDst = "192.168.56.255"
canEthUdpPortDst = 11898

busLogOutputDataCompact = True
