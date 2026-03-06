import serial
import time
import math

class e70:    
    def __init__(self, address: str, port: str, baudrate=115200, timeout=3):
        self.max_range = 40.0 # in um
        self.time_step = 50/1000 # in second
        self.current_x = 0.0
        self.current_y = 0.0
        self.loop_x = ""
        self.loop_y = ""
        self.device_address = address
        self.port = port
        self.baud_rate = baudrate
        self.time_out = timeout
        self.serial_conn = None

    def connect(self):
        """Establish a serial connection."""
        try:
            self.serial_conn = serial.Serial(
                port=self.port,
                baudrate=self.baud_rate,
                timeout=self.time_out
            )
            #print(f"Connected to {self.port} at {self.baudrate} baud.")
            return True
        except serial.SerialException as e:
            raise ConnectionError(f"Failed to connect to device: {e}")
            return False

    def auto_connect(self):
        selected_port = self.port
        available_ports = [port.device for port in serial.tools.list_ports.comports()]
        ports_to_try = []
        if selected_port and selected_port in available_ports:
            ports_to_try.append(selected_port)  
        ports_to_try += [p for p in available_ports if p != selected_port]

        for port in ports_to_try:
            try:
                self.serial_conn = serial.Serial(port=port, baudrate=self.baud_rate, timeout=1, write_timeout=1)
                self.loop_x = self.r_loop()
                if self.loop_x in ("O", "C"):
                    return port
            except serial.SerialException as e:
                continue
        return ""

    def disconnect(self):
        """Close the serial connection."""
        if self.serial_conn and self.serial_conn.is_open:
            self.serial_conn.close()

	# Function to build the data frame
    def build_data_frame(self, function_code: int, data: bytes) -> bytes:
        header = 0xaa
        data_length = len(data)+6

        # Build frame without CRC
        frame = bytearray([header, int(self.device_address), data_length])
        frame.extend(function_code.to_bytes(2, 'little'))  # MSB and LSB of function code
        frame.extend(data)

        # Calculate and append CRC
        crc = self.calculate_crc(frame)  # CRC without header byte
        frame.append(crc)
        return bytes(frame)

    def calculate_crc(self, data: bytes) -> int:
        crc = 0
        for byte in data:
            crc ^= byte
        return crc

    def send_command(self, function_code: int, channel:int, data, waiting_rep=True, read_until=1):
        if isinstance(data, float):
            #payload = bytearray([channel.to_bytes(1), float_to_4bytes(data)])
            payload = channel.to_bytes(1) + self.float_to_4bytes(data)
        elif isinstance(data, int):
            if data > 1:
                payload = channel.to_bytes(1) + data.to_bytes(1)
            else:
                payload = channel.to_bytes(1)    
        else:
            raise TypeError("data must be int, float, or bytes")
        frame = self.build_data_frame(function_code, payload)

        #print("Send:", frame.hex())
        self.serial_conn.write(frame)
        
        if waiting_rep:
            response = self.serial_conn.read(read_until)
            #print("Receive:", response.hex())
            return response
        else:
            return ""

    def float_to_4bytes(self, value: float) -> bytes:
        negative = value < 0
        value = abs(value)

        # Integer part
        integer_part = int(value)

        # Fractional part scaled by 10000
        fraction_part = int(round((value - integer_part) * 10000))

        # Split integer into two bytes
        high_int = (integer_part >> 8) & 0x7F  # keep 7 bits
        if negative:
            high_int |= 0x80  # set sign bit

        low_int = integer_part & 0xFF

        # Split fraction into two bytes
        high_frac = (fraction_part >> 8) & 0xFF
        low_frac = fraction_part & 0xFF

        return bytes([high_int, low_int, high_frac, low_frac])

    def bytes_to_float(self, data: bytes) -> float:
        if len(data) != 4:
            raise ValueError("Input must be exactly 4 bytes")

        byte0, byte1, byte2, byte3 = data

        # Extract sign
        negative = (byte0 & 0x80) != 0

        # Remove sign bit from integer high byte
        high_int = byte0 & 0x7F

        # Reconstruct integer part
        integer_part = (high_int << 8) | byte1

        # Reconstruct fraction part
        fraction_part = (byte2 << 8) | byte3

        value = integer_part + fraction_part / 10000.0

        if negative:
            value = -value

        return value

    def r_voltage(self, channel=0):
        function_code = 5
        response = self.send_command(function_code, channel=channel, data=0, read_until=11)
       # print("Receive:", response.hex())
        voltage = response[-5:-1]
        return self.bytes_to_float(voltage)

    def r_distance(self, channel=0):
        function_code = 6
        response = self.send_command(function_code, channel=channel, data=0, read_until=11)
        distance = response[-5:-1]
        return self.bytes_to_float(distance)

    def r_loop(self, channel=0):
        function_code = 19
        response = self.send_command(function_code, channel=channel, data=0, read_until=8)
        loop = response[-2:-1]
        return loop.decode('ascii')
        
    def r_analog_digital_control(self, channel=0):
        function_code = 23
        self.send_command(function_code, channel=channel, data=0)

    def set_voltage(self, channel=0, voltage=0.0):
        function_code = 0
        self.send_command(function_code, channel=channel, data=voltage, waiting_rep=False)
        time.sleep(self.time_step)

    def set_distance(self, channel=0, distance=0.0):
        function_code = 1
        self.send_command(function_code, channel=channel, data=distance, waiting_rep=False)
        time.sleep(self.time_step)

    def set_loop(self, channel=0, loop="C"):
        function_code = 18
        self.send_command(function_code, channel=channel, data=ord(loop), waiting_rep=False)

    def initial(self, rate=1):
        if self.loop_x == "O":
            self.set_loop()
            time.sleep(0.05)
        self.loop_y = self.r_loop(channel=1)
        if self.loop_y == "O": 
            self.set_loop(channel=1)
            time.sleep(0.05)
        self.current_x = self.r_distance()
        time.sleep(0.05)
        self.current_y = self.r_distance(channel=1)
        #print(f"Move to xy: {self.max_range/2}, {self.max_range/2}")
        self.move_to(target_x=self.max_range/2, target_y=self.max_range/2, step_size=0.5)

    def move_to(self, target_x=0.0, target_y=0.0, step_size=0.1, tol=5e-4):
        
        if not (0 <= target_x <= self.max_range):
            raise ValueError(f"Target X {target_x} outside travel range")

        if not (0 <= target_y <= self.max_range):
            raise ValueError(f"Target Y {target_y} outside travel range")

        x = self.current_x
        y = self.current_y

        dx = target_x - x
        dy = target_y - y

        # -------------------------
        # Case 1: No movement
        # -------------------------
        if abs(dx) < tol and abs(dy) < tol:
            return False

        # -------------------------
        # Case 2: Pure X motion
        # -------------------------
        if abs(dy) < tol:
            direction = 1 if dx > 0 else -1
            total_dist = abs(dx)
            steps = int(abs(dx) / step_size)
            remainder = total_dist - steps * step_size

            for _ in range(steps):
                x += direction * step_size
                #print(f"Set x_: {x}")
                self.set_distance(0, x)
                self.current_x = x
                #x = self.r_distance()
                #print(f"Get x_: {x}")

            if remainder > tol:
                #print(f"Set x_: {x}")
                self.set_distance(0, target_x)
                #x = self.r_distance()
                #print(f"Get x_: {x}")
            self.current_x = target_x
            return True

        # -------------------------
        # Case 3: Pure Y motion
        # -------------------------
        if abs(dx) < tol:
            direction = 1 if dy > 0 else -1
            total_dist = abs(dy)
            steps = int(abs(dy) / step_size)
            remainder = total_dist - steps * step_size

            for _ in range(steps):
                y += direction * step_size
                #print(f"Set _y: {y}")
                self.set_distance(1, y)
                self.current_y = y
                #y = self.r_distance(channel = 1)
                #print(f"Get _y: {y}")

            if remainder > tol:
                #print(f"Set _y: {y}")
                self.set_distance(1, target_y)
                #y = self.r_distance(channel = 1)
                #print(f"Get _y: {y}")
            self.current_y = target_y
            return True

        # -------------------------
        # Case 4: True 2D motion
        # -------------------------
        distance = math.sqrt(dx**2 + dy**2)
        ux = dx / distance
        uy = dy / distance

        steps = int(distance / step_size)
        remainder = distance - steps * step_size

        for _ in range(steps):
            x += ux * step_size
            y += uy * step_size
            #print(f"Set xy: {x}, {y}")
            self.set_distance(0, x)
            self.set_distance(1, y)
            self.current_x = x
            self.current_y = y
            #x = self.r_distance()
            #y = self.r_distance(channel = 1)
            #print(f"Get xy: {x}, {y}")

        # Final correction
        if remainder > tol:
            #print(f"Set xy: {target_x}, {target_y}")
            self.set_distance(0, target_x)
            self.set_distance(1, target_y)
            #x = self.r_distance()
            #y = self.r_distance(channel = 1)
            #print(f"Get xy: {x}, {y}")

        self.current_x = target_x
        self.current_y = target_y
        return True
