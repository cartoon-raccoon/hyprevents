import hid

from hyprevents.event import HyprEvent
from hyprevents.dispatcher import Dispatcher
from hyprevents import logger as mainlogger

logger = mainlogger.getChild("duckypad")

def pad64(data):
    """_Pads a bytearray to 64 bytes._

    Args:
        data (_bytes_): _The data to be padded._

    Returns:
        _bytes_: _The original data passed in, zero-padded to 64 bytes._
    """
    assert len(data) <= 64
    return data + (b'\x00' * (64 - len(data)))

CODE_SUCCESS = 0
CODE_ERROR = 1
CODE_BUSY = 2

class DuckyPadErr(Exception):
    message_dict = {
        0 : "Success",
        1 : "DuckyPad encountered an error",
        2 : "DuckyPad is busy"
    }
    def __init__(self, errorcode, message=None):
        self.errcode = errorcode
        self.message = message if message is not None else self.message_dict[errorcode]
        
    def __repr__(self):
        return f"DuckyPadErr({self.errcode}, {self.message})"
    
    def __str__(self):
        return self.message


class DuckyPad(Dispatcher):
    PC_TO_DPAD_BUFSIZE = 64
    DUCKYPAD_MANFID = 0x0483
    DUCKYPAD_PRODID = 0xd11d
    DUCKYPAD_MANFNAME = "dekuNukem"
    USAGE_ID = b'\x05'
    
    def __init__(self, config=None):
        h = hid.device()
        try:
            h.open(self.DUCKYPAD_MANFID, self.DUCKYPAD_PRODID)
        except Exception as e:
            logger.error(e)
            raise e
        
        if h.get_manufacturer_string() != self.DUCKYPAD_MANFNAME:
            raise Exception("Expected manufacturer string 'dekuNukem'")
        
        logger.debug("Device Info:")
        logger.debug(f"Manufacturer: {h.get_manufacturer_string()}")
        logger.debug(f"Product: {h.get_product_string()}")
        logger.debug(f"Serial No.: {h.get_serial_number_string()}")
        
        h.set_nonblocking(0)
        
        self.duckypad = h
        if config is not None:
            self.subscribes = config["subscribes"]
            self.default = config["default"]
            self.mappings = config["mappings"]
            self.actives = config["active"]
        
        logger.debug(config)
        logger.debug(self.query_info())
        
    
    def load_config(self, config):
        self.subscribes = config["subscribes"]
        self.default = config["default"]
        self.mappings = config["mappings"]
        self.actives = config["active"]


    def handle_event(self, event: HyprEvent):
        logger.debug(">>>>> handle_event start <<<<<")
        logger.debug(f"Got event of type {event.name} with data {event.data}")
        if event.name not in self.subscribes:
            return
        
        if event.name == "activewindow" and self.actives["switching"]:
            tokens = event.data.split(",")
            wincls = tokens[0]
            wintitle = ",".join(tokens[1:])
            logger.debug(f"Got window class '{wincls}' and window title '{wintitle}'")
            
            if wincls in self.mappings:
                if isinstance(self.mappings[wincls], dict):
                    logger.debug("wincls matched with a dict, need to further match on title")
                    # todo
                    return
                else:
                    profile = self.mappings[wincls]
            else:
                profile = self.default
            try:
                self.goto_profile(profile)
            except DuckyPadErr as e:
                if e.errcode != 2:
                    raise e
                logger.debug(f"DuckyPad busy while trying to go to profile {profile}")
        elif event.name == "custom" and self.actives["sleep"]:
            if event.data == "sleep":
                self.sleep()
            elif event.data == "wake":
                self.wake()
            # do not raise error on unrecognized event data,
            # since all dispatchers share the same custom event


    def query_info(self):
        buf = self.USAGE_ID + b'\x00\x00'
        result = self._run_command(buf)
        return {
            "firmware-version-maj" : result[3],
            "firmware-version-min" : result[4],
            "firmware-version-patch" : result[5],
            "hardware-revision" : "duckyPad" if result[6] == 20 else "duckyPad Pro",
            "serial-no" : result[7:11],
            "current-profile" : result[11],
            "is-sleeping" : True if result[12] else False
        }

        
    def goto_profile(self, profile):
        if isinstance(profile, int):
            if profile > 64:
                raise ValueError("profile number cannot be larger than 64")
            buf = self.USAGE_ID + b'\x00\x01'
            buf += profile.to_bytes(1, "little")
        elif isinstance(profile, str):
            buf = self.USAGE_ID + b'\x00\x17'
            buf += profile.encode("ascii")
        else:
            raise TypeError("profile must be int or str")
        
        logger.debug(f"Goto profile command: {buf}")
        self._run_command(buf)
        
    
    def prev_profile(self):
        pass
    

    def next_profile(self):
        pass
    
    
    def sleep(self):
        buf = self.USAGE_ID + b'\x00\x15'
        self._run_command(buf)
    
    
    def wake(self):
        buf = self.USAGE_ID + b'\x00\x16'
        self._run_command(buf)


    def _run_command(self, command):
        logger.debug("Sending command")
        fin = pad64(command)
        logger.debug(f"Bytes to send: {fin}")
        assert len(fin) == 64
        self.duckypad.write(fin)
        reply = self.duckypad.read(64)
        logger.debug(f"Got reply {reply}")
        
        if reply[2] > 0:
            raise DuckyPadErr(reply[2])
        
        return bytes(reply)

handler = DuckyPad()

__name__ = "duckypad"
__all__ = [DuckyPad, DuckyPadErr, handler]
