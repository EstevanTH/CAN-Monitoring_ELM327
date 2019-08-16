import threading
from datetime import datetime
from utility import printT
from traceback import format_exc

try:
	import socket
except ImportError:
	socket = None

# Libpcap - Global Header
# https://wiki.wireshark.org/Development/LibpcapFileFormat#Global_Header
pcap_hdr_t = bytearray( 24 )
pcap_hdr_t[0:4]   = ( 0xa1b2c3d4 ).to_bytes( 4, "big", signed=False ) # magic_number
pcap_hdr_t[4:6]   = ( 2 ).to_bytes( 2, "big", signed=False ) # version_major
pcap_hdr_t[6:8]   = ( 4 ).to_bytes( 2, "big", signed=False ) # version_minor
pcap_hdr_t[8:12]  = ( 0 ).to_bytes( 4, "big", signed=True )  # thiszone
pcap_hdr_t[12:16] = ( 0 ).to_bytes( 4, "big", signed=False ) # sigfigs
pcap_hdr_t[16:20] = ( 32 ).to_bytes( 4, "big", signed=False ) # snaplen
pcap_hdr_t[20:24] = ( 227 ).to_bytes( 4, "big", signed=False ) # network = LINKTYPE_CAN_SOCKETCAN
pcap_hdr_t = bytes( pcap_hdr_t )

# Libpcap - Record (Packet) Header
# https://wiki.wireshark.org/Development/LibpcapFileFormat#Record_.28Packet.29_Header
# http://www.tcpdump.org/linktypes/LINKTYPE_CAN_SOCKETCAN.html
class pcaprec_CAN( bytearray ):
	def __init__( self, frame ):
		dataLen = len( frame.data )
		super().__init__( 24+dataLen )
		
		# Portion pcaprec_hdr_t
		self[0:4]   = ( int( frame.time ) ).to_bytes( 4, "big", signed=False ) # ts_sec
		self[4:8]   = ( int( ( frame.time%1 )*1000000 ) ).to_bytes( 4, "big", signed=False ) # ts_usec
		self[8:12]  = ( 8+dataLen ).to_bytes( 4, "big", signed=False ) # incl_len
		self[12:16] = ( 8+dataLen ).to_bytes( 4, "big", signed=False )  # orig_len
		
		# Portion content
		canFlagsId = frame.identifier
		if frame.isRTR:
			canFlagsId |= 0x40000000
		if frame.isExtended:
			canFlagsId |= 0x80000000
		self[16:20] = ( canFlagsId ).to_bytes( 4, "big", signed=False ) # CAN ID and flags
		self[20] = frame.DLC # Frame payload length
		if dataLen:
			self[24:24+dataLen] = frame.data # Payload

# CAN-ETH - Packet of 1 CAN frame
# https://www.proconx.com/assets/files/products/caneth/canframe.pdf
canEthBasePacket = bytearray( 25 )
canEthBasePacket[0:8] = b"ISO11898" # MagicId
canEthBasePacket[8] = 1 # Version
canEthBasePacket[9] = 1 # Cnt
canEthBasePacket = bytes( canEthBasePacket )
class canEthPacket( bytearray ):
	_basePacket = canEthBasePacket
	
	def __init__( self, frame ):
		super().__init__( type( self )._basePacket )
		
		# Bytes left alone have a value of 0.
		self[10:14] = ( frame.identifier ).to_bytes( 4, "little", signed=False ) # Id
		self[14] = frame.DLC # Cnt
		dataLen = len( frame.data )
		if dataLen:
			self[15:15+dataLen] = frame.data # CanBytes
		if frame.isExtended:
			self[23] = 1 # ExtFlag
		if frame.isRTR:
			self[24] = 1 # RtrFlag
del canEthBasePacket

class CANToNetworkThread( threading.Thread ):
	""" Thread class that encapsulates CAN frames
	Depending on the configuration:
	- It dispatches CAN-ETH packets to an IP address:port destination.
	- It generates CAN libpcap files (compatible with Wireshark).
	"""
	daemon = False
	
	def __init__( self ):
		threading.Thread.__init__( self )
		
		self.pendingData = []
		self.pendingDataLock = threading.Lock()
		
		self.continueProcessLock = threading.Lock()
		self.continueProcessLock.acquire()
		self.terminating = False
		self.parametersLock = threading.Lock()
		
		self.logOutputDataFileName = None
		self.logOutputDataFile = None
		self.netOutputConfig = None
		self.netOutputSocket = None
	
	def setParameters( self, parameters ):
		with self.parametersLock:
			pcapOutputFile = parameters["pcapOutputFile"]
			if pcapOutputFile!=self.logOutputDataFileName:
				self.logOutputDataFileName = pcapOutputFile
				# Close any open file:
				if self.logOutputDataFile is not None:
					try:
						self.logOutputDataFile.close()
					except:
						pass
					self.logOutputDataFile = None
				# Attempt to open file:
				if self.logOutputDataFileName is not None:
					try:
						self.logOutputDataFile = open( self.logOutputDataFileName, mode="wb" )
						self.logOutputDataFile.write( pcap_hdr_t )
					except Exception as e:
						self.logOutputDataFile = None
						printT( "Unable to open the pcapOutputFile file:", e )
				# Cleanup for clean start:
			if socket:
				canEthUdpEnabled = parameters.get( "canEthUdpEnabled", False )
				canEthUdpIpVersion = parameters.get( "canEthUdpIpVersion", 4 )
				if canEthUdpIpVersion==6:
					canEthUdpIpVersion = socket.AF_INET6
				elif canEthUdpIpVersion==4:
					canEthUdpIpVersion = socket.AF_INET
				canEthUdpAddrSrc = parameters.get( "canEthUdpAddrSrc", None )
				canEthUdpPortSrc = parameters.get( "canEthUdpPortSrc", None )
				canEthUdpAddrDst = parameters.get( "canEthUdpAddrDst", canEthUdpIpVersion==socket.AF_INET6 and "::1" or "127.0.0.1" )
				canEthUdpPortDst = parameters.get( "canEthUdpPortDst", 11898 )
				netOutputConfig = (
					canEthUdpEnabled,
					canEthUdpIpVersion,
					canEthUdpAddrSrc,
					canEthUdpPortSrc,
					canEthUdpAddrDst,
					canEthUdpPortDst,
				)
				if not self.netOutputSocket or netOutputConfig!=self.netOutputConfig:
					if self.netOutputSocket:
						self.netOutputSocket.close()
						self.netOutputSocket = None
					if canEthUdpEnabled:
						try:
							netOutputSocket = None
							netOutputSocket = socket.socket( canEthUdpIpVersion, socket.SOCK_DGRAM )
							netOutputSocket.setsockopt( socket.SOL_SOCKET, socket.SO_REUSEADDR, 1 )
							if canEthUdpAddrSrc and canEthUdpPortSrc:
								netOutputSocket.bind( (canEthUdpAddrSrc, canEthUdpPortSrc) )
							self.canEthUdpDst = (canEthUdpAddrDst, canEthUdpPortDst)
							self.netOutputSocket = netOutputSocket
						except:
							printT( format_exc() )
							try:
								netOutputSocket.close()
							except:
								pass
					self.netOutputConfig = netOutputConfig
	
	def logFrame( self, frame ):
		if self.logOutputDataFile is not None:
			with self.pendingDataLock:
				self.pendingData.append( frame )
			try:
				self.continueProcessLock.release()
			except RuntimeError:
				pass
	
	def terminate( self ):
		self.terminating = True
		try:
			self.continueProcessLock.release()
		except RuntimeError:
			pass
	
	def run( self ):
		while not self.terminating:
			self.continueProcessLock.acquire()
			presentPendingData = True
			with self.parametersLock:
				while presentPendingData:
					with self.pendingDataLock:
						pendingData = self.pendingData
						self.pendingData = [] # cleanup
					presentPendingData = len( pendingData )!=0
					if self.netOutputSocket:
						for frame in pendingData:
							try:
								self.netOutputSocket.sendto( canEthPacket( frame ), self.canEthUdpDst )
							except OSError as e:
								# network error silently discarded
								pass
							except Exception as e:
								printT( "CAN-ETH converter error, stopping:", format_exc() )
								try:
									netOutputSocket = self.netOutputSocket
									self.netOutputSocket = None
									netOutputSocket.close()
								except:
									pass
								break
					packet = None
					if self.logOutputDataFile:
						for frame in pendingData:
							try:
								self.logOutputDataFile.write( pcaprec_CAN( frame ) )
							except Exception as e:
								printT( "LibPCAP logging error, stopping:", format_exc() )
								try:
									logOutputDataFile = self.logOutputDataFile
									self.logOutputDataFile = None
									logOutputDataFile.close()
								except:
									pass
		try:
			self.logOutputDataFile.close() # properly flush & close
		except:
			pass
