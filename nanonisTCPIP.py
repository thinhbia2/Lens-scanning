import socket
import struct

class nanonisTCP:    
    def __init__(self, ip = '127.0.0.1', port = 6501, max_buf_size = 1024):
        """Initialize the NanonisTCPIP class with the IP and port."""
        self.ip = ip
        self.port = port
        self.sock = None
        self.max_buf_size = max_buf_size  # Default buffer size; you can adjust it as needed
        
    def connect(self):
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(5.0)
            self.sock.connect((self.ip, self.port))
            print(f"Connected to {self.ip}:{self.port}")
            return True
        except socket.timeout:
            raise TimeoutError(f"Connection to {self.ip}:{self.port} timed out")
            self.sock = None
            return False
        except socket.error as e:
            raise ConnectionError(f"Failed to connect to {self.ip}:{self.port}: {e}")
            self.sock = None
            return False

    def send_command(self, message):
        try:
            self.sock.settimeout(2.0)
            self.sock.sendall(bytes.fromhex(message))
        except socket.timeout:
            print("Client 1: Send operation timed out.")
        except socket.error as e:
            print(f"Client 1: Socket error during send: {e}")

    def receive_response(self, error_index=-1, keep_header = False):
        """
        Parameters
        error_index : index of 'error status' within the body. -1 skip check
        keep_header : if true: return entire response. if false: return body
        
        Returns
        response    : either header + body or body only (keep_header)
        
        """
        try:
            self.sock.settimeout(2.0)
            response = self.sock.recv(self.max_buf_size)                               # Read the response
        except socket.timeout:
            print("Client 1: Receive operation timed out.")
        except socket.error as e:
            print(f"Client 1: Socket error during receive: {e}")
        body_size = self.hex_to_int32(response[32:36])
        while(True): 
            if(len(response) == body_size + 40): break                          # body_size + header size (40)
            response += self.sock.recv(self.max_buf_size)
        
        if(error_index > -1): self.check_error(response[40:],error_index)       # error_index < 0 skips error check
        
        if(not keep_header):
            return response[40:]                                                # Header is fixed to 40 bytes - drop it
        
        return response

    def check_error(self,response,error_index):
        """
        Checks the response from nanonis for error messages

        Parameters
        response : response body (not inc. header) from nanonis (bytes)
        error_index : index of error status within the body

        Raises
        Exception   : error message returned from Nanonis

        """
        i = error_index                                                         # error_index points to start-byte in the body, which is after the 40-byte header
        error_status = self.hex_to_uint16(response[i:i+4])                      # error_status is 4 bytes long
        
        if(error_status):
            i += 8                                                              # index of error description is 8 bytes after error status
            error_description = response[i:].decode()                           # just grab from start index to the end of the message
            raise Exception(error_description)                                  # raise the exception
                
    def close_socket(self):
        """ Close the socket """
        if self.sock:
            self.sock.close()

    def hex_to_int32(self,h32):
        return struct.unpack("<i",struct.pack("I",int("0x"+h32.hex(),16)))[0]

    def to_hex(self,conv,num_bytes):
        if(conv >= 0): return hex(conv)[2:].zfill(2*num_bytes)
        if(conv < 0):  return hex((conv + (1 << 8*num_bytes)) % (1 << 8*num_bytes))[2:]

    def float64_to_hex(self,f64):
        # see https://stackoverflow.com/questions/23624212/how-to-convert-a-float-into-hex
        if(f64 == 0): return "0000000000000000"                                 # workaround for zero. look into this later
        return hex(struct.unpack('<Q', struct.pack('<d', f64))[0])[2:] 

    def hex_to_uint16(self,h16):
        return struct.unpack("<H",struct.pack("H",int("0x"+h16.hex(),16)))[0]
        
    def hex_to_float32(self,h32):
        # see https://forum.inductiveautomation.com/t/ieee-754-standard-converting-64-bit-hex-to-decimal/9324/3
        return struct.unpack("<f", struct.pack("I",int("0x"+h32.hex(), 16)))[0]        

    def make_header(self, command_name, body_size, resp=True):
        """
        Parameters
        command_name : name of the Nanonis function
        body_size    : size of the message body in bytes
        resp         : tell nanonis to send a response. response contains error
                       message so will nearly always want to receive it

        Returns
        hex_rep : hex representation of the header string
        """ 
        hex_rep = command_name.encode('utf-8').hex()                            # command name
        hex_rep += "{0:#0{1}}".format(0,(64 - len(hex_rep)))                    # command name (fixed 32)
        hex_rep += self.to_hex(body_size, 4)                                    # Body size (fixed 4)
        hex_rep += self.to_hex(resp, 2)                                         # Send response (fixed 2)
        hex_rep += "{0:#0{1}}".format(0, 4)                                     # not used (fixed 2)
        return hex_rep

class FolMe:
    def __init__(self, nanonisTCP):
        self.nanonisTCP = nanonisTCP

    def XYPosSet(self, X, Y, Wait_end_of_move=False):
        """
        This function moves the tip to the specified X and Y target coordinates
        (in meters). It moves at the speed specified by the "Speed" parameter
        in the Follow Me mode of the Scan Control module. This function will 
        return when the tip reaches its destination or if the movement stops.

        Parameters
        X : Set x position (m)
        Y : Set y position (m)
        Wait_end_of_move : False: Selects whether the function  immediately
                           True: Waits until tip stops moving
        """
        ## Make Header
        hex_rep = self.nanonisTCP.make_header('FolMe.XYPosSet', body_size=20)
        
        ## arguments
        hex_rep += self.nanonisTCP.float64_to_hex(X)
        hex_rep += self.nanonisTCP.float64_to_hex(Y)
        hex_rep += self.nanonisTCP.to_hex(Wait_end_of_move,4)
        
        self.nanonisTCP.send_command(hex_rep)
        message =  self.nanonisTCP.receive_response(0)
        return message

class Current:
    """
    Nanonis Current Module
    """
    def __init__(self,NanonisTCP):
        self.NanonisTCP = NanonisTCP
    
    def Get(self):
        """
        Returns the tunnelling current value

        Returns
        -------
        current : Current value (A)

        """
        ## Make Header
        hex_rep = self.NanonisTCP.make_header('Current.Get', body_size=0)        
        self.NanonisTCP.send_command(hex_rep)        
        response = self.NanonisTCP.receive_response(4)        
        current = self.NanonisTCP.hex_to_float32(response[0:4])        
        return current
    
    def Get100(self):
        """
        Returns the current value of the "Current 100" module

        Returns
        -------
        current100 : Current 100 value (A)

        """
        ## Make Header
        hex_rep = self.NanonisTCP.make_header('Current.100Get', body_size=0)        
        self.NanonisTCP.send_command(hex_rep)        
        response = self.NanonisTCP.receive_response(4)        
        current100 = self.NanonisTCP.hex_to_float32(response[0:4])        
        return current100
    
    def BEEMGet(self):
        """
        Returns the BEEM current value of the corresponding module in a BEEM
        system

        Returns
        -------
        currentBEEM : Current BEEM value (A)

        """
        ## Make Header
        hex_rep = self.NanonisTCP.make_header('Current.BEEMGet', body_size=0)        
        self.NanonisTCP.send_command(hex_rep)        
        response = self.NanonisTCP.receive_response(4)        
        currentBEEM = self.NanonisTCP.hex_to_float32(response[0:4])        
        return currentBEEM
    
    def GainSet(self,gain_index):
        """
        Sets the gain of the current amplifier

        Parameters
        ----------
        gain_index : The index out of the list of gains which can be retrieved
                     by the function Current.GainsGet

        """
        ## Make Header
        hex_rep = self.NanonisTCP.make_header('Current.GainSet', body_size=2)        
        ## Arguments
        hex_rep += self.NanonisTCP.to_hex(gain_index,2)        
        self.NanonisTCP.send_command(hex_rep)        
        self.NanonisTCP.receive_response(0)
    
    def GainsGet(self):
        """
        Returns the selectable gains of the current amplifier and the index of 
        the selected one

        Returns
        -------
        gains      : array of selectable gains
        gain_index : index of the selected gain in gains array

        """
        ## Make Header
        hex_rep = self.NanonisTCP.make_header('Current.GainsGet', body_size=0)        
        self.NanonisTCP.send_command(hex_rep)        
        response = self.NanonisTCP.receive_response()        
        # gains_size      = self.NanonisTCP.hex_to_int32(response[0:4])         # Not needed since
        number_of_gains = self.NanonisTCP.hex_to_int32(response[4:8])           # We know the number of gains
        
        idx   = 8
        gains = []
        for g in range(number_of_gains):
            size = self.NanonisTCP.hex_to_int32(response[idx:idx+4])            # And the size of each next gain
            idx += 4
            gain = response[idx:idx+size].decode()
            idx += size
            gains.append(gain)
        
        gain_index = self.NanonisTCP.hex_to_uint16(response[idx:idx+2])        
        return [gains,gain_index]
    
    def CalibrSet(self,calibration,offset):
        """
        Sets the calibration and offset of the selected gain in the current 
        module

        Parameters
        ----------
        calibration : calibration factor (A/V)
        offset      : offset (A)

        """
        ## Make Header
        hex_rep = self.NanonisTCP.make_header('Current.CalibrSet', body_size=16)        
        ## Arguments
        hex_rep += self.NanonisTCP.float64_to_hex(calibration)
        hex_rep += self.NanonisTCP.float64_to_hex(offset)        
        self.NanonisTCP.send_command(hex_rep)        
        self.NanonisTCP.receive_response(0)
    
    def CalibrGet(self):
        """
        Gets the calibration and offset of the selected gain in the current 
        module

        Returns
        -------
        callibtation : calibration (A/V)
        offset       : offset (A)

        """
        ## Make Header
        hex_rep = self.NanonisTCP.make_header('Current.CalibrGet', body_size=0)        
        self.NanonisTCP.send_command(hex_rep)        
        response = self.NanonisTCP.receive_response(16)        
        calibration = self.NanonisTCP.hex_to_float64(response[0:8])
        offset      = self.NanonisTCP.hex_to_float64(response[8:16])
        
        return [calibration,offset]

class ZCtrl:
    def __init__(self, nanonisTCP):
        self.nanonisTCP = nanonisTCP

    def ZPosGet(self):
        """
        Returns the current Z position of the tip

        Returns
        -------
        zpos : the current z position of the tip

        """
        ## Make Header
        hex_rep = self.nanonisTCP.make_header('ZCtrl.ZPosGet', body_size=0)
        self.nanonisTCP.send_command(hex_rep)
        response = self.nanonisTCP.receive_response(4)
        zpos = self.nanonisTCP.hex_to_float32(response[0:4])        
        return zpos  
