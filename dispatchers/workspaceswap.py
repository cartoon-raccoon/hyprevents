import re
import logging

from hyprevents.event import HyprEvent
from hyprevents.dispatcher import Dispatcher
from hyprevents import get_eventhandler, logger as mainlogger

eventhandler = get_eventhandler()
logger = mainlogger.getChild("workspaceswap")
logger.setLevel(logging.WARNING)

def parse_focusedmon_data(data):
    s = data.split(",")
    return s[0], int(s[1])


def parse_moveworkspace_data(data):
    s = data.split(",")
    return int(s[0]), s[1], s[2]


class Monitor(object):
    def __init__(self, name, id, wkspc=None):
        self.name, self.id = name, id
        self.curr_wkspc = wkspc
        self.prev_wkspc = None
        
        
    def __repr__(self):
        return f"Monitor(name={self.name}, id={self.id}, curr_wkspc={self.curr_wkspc}, prev_wkspc={self.prev_wkspc})"
            
            
    def set_curr_wkspc(self, wkspc):
        if self.curr_wkspc != wkspc:    
            self.prev_wkspc = self.curr_wkspc
            self.curr_wkspc = wkspc
            
        assert self.curr_wkspc != self.prev_wkspc


class WorkspaceSwap(Dispatcher):
    def __init__(self, config=None):
        if config is not None:
            self.load_config(config)
        
    
    def load_config(self, config):
        data_regex = config["swap-ev"]["data"]
        logger.debug(f"got data regex {data_regex}")
        self.triggerdata = re.compile(data_regex)
        
        activews = eventhandler.send_hyprland_cmd("activeworkspace")
        allmonitorinfo = eventhandler.send_hyprland_cmd("monitors")
        
        logger.debug(f"Got current active monitor {activews}")
        self.currentmon = Monitor(activews["monitor"], activews["monitorID"], activews["id"])
        
        self.monitors = dict()
        for mon in allmonitorinfo:
            self.monitors[mon["name"]] = Monitor(mon["name"], mon["id"], mon["activeWorkspace"]["id"])
        logger.debug(f"Got monitors {self.monitors}")
    
    
    def handle_event(self, event: HyprEvent):
        logger.debug(">>>>> handle_event start <<<<<")
        if event.name == "focusedmon":
            # set current focused monitor info
            monname, wkspcid = parse_focusedmon_data(event.data)
            logger.debug(f"Focused monitor change, got event data monname={monname}, workspace={wkspcid}")
            self.currentmon = self.monitors[monname]
            logger.debug(f"Active monitor: {self.currentmon}")
            
        elif event.name == "workspace":
            wkspcid = int(event.data)
            logger.debug(f"Workspace change on focused monitor {self.currentmon.name}, got event data wkspcid={wkspcid}")
            self.currentmon.set_curr_wkspc(wkspcid)
            logger.debug(f"Active monitor: {self.currentmon}")
            logger.debug(self.monitors)
            
        elif event.name == "moveworkspacev2":
            wkspcid, _, monname = parse_moveworkspace_data(event.data)
            logger.debug(f"Workspace {wkspcid} moved to monitor {monname}")
            # we should get always get 2 moveworkspacev2 events each time
            self.monitors[monname].set_curr_wkspc(wkspcid)
            
        elif event.name == "custom":
            # check if data is "movewkspc"; if so, run the workspace change
            m = self.triggerdata.search(event.data)
            if m is None:
                return
            
            try:
                new_wkspc = int(m.group(1))
            except ValueError:
                logger.error(f"unable to get new workspace, got data {m.group(1)}")
                return
            
            self.do_workspace_change(new_wkspc)
        
        logger.debug(self.monitors)
        logger.debug(f"Current active monitor: {self.currentmon.name}")
            
    
    def update_monitor_info(self):
        moninfo = eventhandler.send_hyprland_cmd("monitors")
        for mon in moninfo:
            if mon["name"] in self.monitors:
                monitor = self.monitors[mon["name"]]
                monitor.set_curr_wkspc(mon["activeWorkspace"]["id"])
            else:
                self.monitors[mon["name"]] = Monitor(mon["name"], mon["id"], mon["activeWorkspace"]["id"])
        activews = eventhandler.send_hyprland_cmd("activeworkspace")
        self.currentmon.name = activews["monitor"]
        self.currentmon.id = activews["monitorID"]
        self.currentmon.set_curr_wkspc(activews["id"])
    
    
    def find_monitor_by_id(self, mon_id: int) -> Monitor:
        for mon in self.monitors.values():
            if mon["id"] == mon_id:
                return mon

      
    def find_wkspc_mon(self, wkspcid, prev=False) -> Monitor:
        """
        Find the monitor that `wkspcid` is an active workspace on.
        
        Returns the monitor object if `wkspcid` corresponds to an active workspace,
        else returns None.
        """
        for mon in self.monitors.values():
            if prev:
                if mon.prev_wkspc == wkspcid:
                    return mon
            else:
                if mon.curr_wkspc == wkspcid:
                    return mon
        return None
       
     
    def do_workspace_change(self, wkspcid):
        """
        Changes the current active workspace on the active monitor.
        """
        logger.debug(f"changing to workspace {wkspcid} on active monitor {self.currentmon.name}")
        
        self.update_monitor_info()
        othermon = self.find_wkspc_mon(wkspcid)
        logger.debug(f"Other monitor: {othermon}")
        logger.debug(f"Current monitor: {self.currentmon}")
        
        # the selected workspace is active on current monitor
        if othermon is not None and othermon.name == self.currentmon.name:
            # do not swap, instead go to prev
            new_wkspcid = self.currentmon.prev_wkspc
            logger.debug(
                f"Wkspc {wkspcid} already active on current mon {self.currentmon.name}, changing to prev wkspc {new_wkspcid}"
            )
            if new_wkspcid is None:
                logger.debug("No previous workspace found, no action taken")
                return
            # recurse with previous workspace
            self.do_workspace_change(new_wkspcid)
        else:
            self.focus_workspace_on_current_mon(wkspcid)
    
    
    def focus_workspace_on_current_mon(self, wkspcid):
        logger.debug(f"Focusing workspace {wkspcid} on current monitor {self.currentmon.name}")
        eventhandler.send_hyprland_cmd(f"dispatch focusworkspaceoncurrentmonitor {wkspcid}")
        
                
    
handler = WorkspaceSwap()

__name__ = "workspaceswap"
__all__ = [WorkspaceSwap, handler]