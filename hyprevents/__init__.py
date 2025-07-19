#!/usr/bin/env python3

import os
import sys
import logging
import socket
import importlib
import subprocess
import re
import toml
import json
from typing import *

from hyprevents.event import HyprEvent
from hyprevents.notifications import HyprlandNotifType as Notif
from hyprevents.dispatcher import Dispatcher

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

HOME_DIR = os.environ["HOME"]
CONFIG_DIR = f"{HOME_DIR}/.config/hyprevents"


def load_plugin_as_module(plugin_name):
    logger.debug(f"Loading dispatcher module {CONFIG_DIR}/dispatchers/{plugin_name}.py")
    spec = importlib.util.spec_from_file_location(plugin_name, f"{CONFIG_DIR}/dispatchers/{plugin_name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module.__name__] = module
    logger.debug(f"Loading module with name {module.__name__}")
    spec.loader.exec_module(module)
    return module


def get_eventhandler():
    return eventhandler


class HyprIPCError(Exception):
    def __init__(self, msg, errcode):
        self.msg = msg
        self.errcode = errcode
        

    def __str__(self):
        return f"hyprctl terminated with errcode {self.errcode}: {self.msg}"
        
    
    def __repr__(self):
        return f"HyprIPCError(msg={self.msg}, errcode={self.errcode})"


class EventHandler:
    
    HYPRLAND_ENV = "HYPRLAND_INSTANCE_SIGNATURE"
    RUNTIME_DIR_ENV = "XDG_RUNTIME_DIR"
    
    def __init__(self, config=None):
        try:
            self.his = os.environ[self.HYPRLAND_ENV]
        except KeyError:
            logging.error("A hyprland instance does not seem to be running")
            sys.exit(1)
        try:
            self.runtime_dir = os.environ[self.RUNTIME_DIR_ENV]
        except KeyError:
            my_uid = os.getuid();
            logging.debug(f"Got UID {my_uid}")
            logging.warning(f"XDG_RUNTIME_DIR not set, setting default using UID {my_uid}")
            self.runtime_dir = f"/run/user/{my_uid}"
            
        self.connect_to_hyprland()
        
        try:
            if config is None:
                self.config = toml.load(f"{CONFIG_DIR}/config.toml")
            else:
                self.config = toml.load(config)
        except toml.TomlDecodeError as e:
            logger.error(e)
            self.send_hyprland_notification(
                "Hyprevents: syntax error in config file",
                Notif.ERROR,
                "ff0000"
            )
            sys.exit(1)
        
        self.dispatchers: Dict[str, List[Dispatcher]] = {}
        self.handlers: Dict[str, Dispatcher] = {}
        
        self.regex1 = re.compile(r"(.+)>>(.+)")
        self.running = True
        
    
    def load_all_dispatchers(self):
        loaded = self.config["general"]["loaded"]
        
        for dispname in loaded:
            try:
                self.load_dispatcher(dispname)
            except Exception:
                continue
        logging.debug(self.dispatchers)
        
        
    def load_dispatcher(self, dispname):
        module = load_plugin_as_module(dispname)
        handler = module.handler
        self.handlers[module.__name__] = handler
        
        try:
            mod_config = self.config[dispname]
        except KeyError:
            logger.error(f"Config for module '{dispname}' not found, skipping")
            raise Exception
        
        handler.load_config(mod_config)
        
        for event in self.config[module.__name__]["subscribes"]:
            logging.debug(f"{module.__name__}: Subscribing to events of type {event}")
            if event in self.dispatchers:
                self.dispatchers[event].append(handler)
            else:
                self.dispatchers[event] = [handler]


    def unload_dispatcher(self, dispname):
        subbed_events = self.config[dispname]["subscribes"]
        dispatcher = self.handlers[dispname]
        for event in subbed_events:
            self.dispatchers[event].remove(dispatcher)
            
        del self.handlers[dispname]
    
    
    def reload_dispatcher_config(self, dispname):
        disp_config = self.config[dispname]
        dispatcher = self.handlers[dispname]
        dispatcher.load_config(disp_config)


    def connect_to_hyprland(self):
        hyprland_eventsock = f"{self.runtime_dir}/hypr/{self.his}/.socket2.sock"
        self.cmdsockpath = f"{self.runtime_dir}/hypr/{self.his}/.socket.sock"
        logging.debug(f"Found hyprland socket directory {hyprland_eventsock}")
        self.eventsock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        if not hasattr(self, "cmdsock"):
            self.cmdsock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.eventsock.connect(hyprland_eventsock)
        
        
    def disconnect_from_hyprland(self):
        self.eventsock.close()
        
        
    def send_hyprland_notification(self, msg, msgtype, color, fontsize=10, time=5000):
        cmd = f"notify {msgtype.value} {time} rgb({color}) fontsize:{fontsize} {msg}"
        self.send_hyprland_cmd(cmd)
        
        
    def send_hyprland_cmd(self, reqs, batch=False, use_json=True):
        args = ["hyprctl"]
        if json:
            args.append("-j")
        if batch:
            args.append("--batch")
            # assume req is a list
            args.append(";".join(reqs))
        else:
            args.append(reqs)
        proc = subprocess.run(args, capture_output=True)
        stdout = proc.stdout.decode("utf-8")
        
        if proc.returncode != 0:
            raise HyprIPCError(proc.stderr.decode("utf-8"), proc.returncode)
        
        # we should only get here if hyprctl ran correctly, so
        # json decode errors should only be because there is no output
        try:
            if batch:
                results = stdout.split("\n\n\n")
                result = {}
                for req, res in zip(reqs, results):
                    result[req] = json.loads(res) if use_json else res
            else:
                result = json.loads(stdout) if use_json else stdout
        except json.decoder.JSONDecodeError:
            return stdout
            
        logger.debug(result)
            
        return result
        
        
    def get_next_event(self):
        # get raw event
        buf = b""
        while True:
            c = self.eventsock.recv(1)
            if c == b"\n":
                break
            else:
                buf += c
                
        rsearch = self.regex1.search(buf.decode("utf-8"))
        if rsearch is None:
            return None
        eventname = rsearch.group(1)
        eventdata = rsearch.group(2)
        
        return HyprEvent(eventname, eventdata)


    def dispatch_event(self, event: HyprEvent):
        if event.name in self.dispatchers:
            for dispatcher in self.dispatchers[event.name]:
                dispatcher.handle_event(event)


    def teardown(self):
        self.eventsock.close()
        
            
    def mainloop(self):
        logger.debug("===== Main Loop Starting =====")
        while self.running:
            try:
                event = self.get_next_event()
                if event is None:
                    continue
                logging.debug(event)
                self.dispatch_event(event)
            except KeyboardInterrupt:
                self.running = False
        
        self.teardown()
        
        
eventhandler = EventHandler()
