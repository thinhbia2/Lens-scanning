import sys
import clr  # clr is part of the pythonnet package
import os
import time
import numpy as np
#from Newport.Motion.CmdLibAgilis import CmdLibAgilis
#from Newport.VCPIOLib import VCPIOLib
from System.Text import StringBuilder

class PiezoUC28:
    def __init__(self, channel=1, dll_path=None):
        """Initialize the wrapper."""
                # Set the default DLL path if not provided
        if dll_path is None:
            dll_path = r"C:\Program Files (x86)\Newport\Piezo Motion Control\AG-UC2-UC8\Bin"
        
        # Add DLL path to the system path
        sys.path.append(dll_path)
        
        # Load the .NET DLLs dynamically
        clr.AddReference(os.path.join(dll_path, "CmdLibAgilis.dll"))
        clr.AddReference(os.path.join(dll_path, "VCPIOLib.dll"))
        
        # Import the necessary classes from the loaded DLLs
        from Newport.Motion.CmdLibAgilis import CmdLibAgilis
        from Newport.VCPIOLib import VCPIOLib

        self.oDeviceIO = VCPIOLib(True)  # Enable logging
        self.oCmdLib = CmdLibAgilis(self.oDeviceIO)
        self.nChannel = channel  # Set the user-defined channel, default is channel 1
        self.knStepAmplitudeMax = 50
        
        #self.discover_and_open_device()

    def discover_and_open_device(self):
        """Discover devices and open the first available one."""
        self.oDeviceIO.DiscoverDevices()
        strDeviceKeyList = np.array ([])
        strDeviceKeyList = self.oDeviceIO.GetDeviceKeys()
        n = -1
        #self.oCmdLib.SetChannel(self.nChannel)

        if not strDeviceKeyList:
            print("No devices discovered.")
            return False
        else:
            for oDeviceKey in strDeviceKeyList:
                strDeviceKey = str(oDeviceKey)
                n = n + 1
                strOut = "Device Key[{}] = {}"
                #print (strOut.format (n, strDeviceKey))
                if self.oCmdLib.Open(strDeviceKey) == 0:
                    bStatus = False
                    strFirmwareVersion = ""
                    bStatus, strFirmwareVersion = self.oCmdLib.GetFirmwareVersion (strFirmwareVersion)

                    # If the firmware version was read
                    if (bStatus) :
                        strOut = "Device ID[{}] = '{}'\n"
                        #print (strOut.format (n, strFirmwareVersion))
                        return True
                        #self.oCmdLib.WriteLog (strOut.format (n, strFirmwareVersion))
                    else :
                        #print ("Could not get the firmware version.\n")
                        return False
        #else:
        #    print("Failed to open the device.")
        #    return False

    def set_remote_mode(self):
        """Set the controller to remote mode."""
        return self.oCmdLib.SetRemoteMode()

    def set_local_mode(self):
        """Set the controller to local mode."""
        return self.oCmdLib.SetLocalMode()

    def set_channel(self):
        """Set the channel."""
        return self.oCmdLib.SetChannel(self.nChannel)

    def get_step_amplitude_negative(self, axis):
        """Get the negative step amplitude for the specified axis."""
        step_amplitude_neg = 0
        success, step_amplitude_neg = self.oCmdLib.GetStepAmplitudeNegative(axis, step_amplitude_neg)
        if success:
            #print(f"Negative step amplitude for axis {axis}: {step_amplitude_neg}")
            return step_amplitude_neg
        else:
            print(f"Failed to get step amplitude for negative axis {axis}.")
            return None

    def set_step_amplitude_negative(self, axis, amplitude):
        """Set the negative step amplitude for the specified axis."""
        success = self.oCmdLib.SetStepAmplitudeNegative(axis, amplitude)
        if success:
            #print(f"Set negative step amplitude to {amplitude} on axis {axis}")
            return True
        else:
            print(f"Failed to set step amplitude on negative axis {axis}.")
            return False

    def get_step_amplitude_positive(self, axis):
        """Get the positive step amplitude for the specified axis."""
        step_amplitude_pos = 0
        success, step_amplitude_pos = self.oCmdLib.GetStepAmplitudePositive(axis, step_amplitude_pos)
        if success:
            #print(f"Positive step amplitude for axis {axis}: {step_amplitude_pos}")
            return step_amplitude_pos
        else:
            print(f"Failed to get step amplitude for positive axis {axis}.")
            return None

    def set_step_amplitude_positive(self, axis, amplitude):
        """Set the positive step amplitude for the specified axis."""
        success = self.oCmdLib.SetStepAmplitudePositive(axis, amplitude)
        if success:
            #print(f"Set positive step amplitude to {amplitude} on axis {axis}")
            return True
        else:
            print(f"Failed to set step amplitude on positive axis {axis}.")
            return False

    def stop_motion(self, axis):
        """Stop motion on the specified axis."""
        success = self.oCmdLib.StopMotion(axis)
        if success:
            #print(f"Motion stopped successfully on axis {axis}.")
            return True
        else:
            print(f"Failed to stop motion on axis {axis}.")
            return False

    def relative_move(self, axis, steps):
        """Perform a relative move by the specified number of steps on the specified axis."""
        success = self.oCmdLib.RelativeMove(axis, steps)
        if success:
            #print(f"Moved {steps} steps relatively on axis {axis}.")
            return True
        else:
            print(f"Failed to perform relative move on axis {axis}.")
            return False

    def shutdown(self):
        """Shutdown the communication and close the device."""
        self.oCmdLib.Close()
        self.oDeviceIO.Shutdown()
        #print("Device communication shut down.")

# Example usage
if __name__ == "__main__":
    controller = PiezoControllerWrapper()
    
    if controller.discover_and_open_device():
        if controller.set_remote_mode():
            axis = int(input("Enter the axis you want to control (e.g., 1 or 2): "))

            # Example: Set amplitudes and move on the specified axis
            controller.set_step_amplitude_negative(axis, 30)
            controller.set_step_amplitude_positive(axis, 30)
            controller.relative_move(axis, 100)
            controller.stop_motion(axis)
        
        controller.shutdown()
