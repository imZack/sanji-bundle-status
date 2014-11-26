#!/usr/bin/env python
# -*- coding: UTF-8 -*-

import logging
import os
import threading
import time
import psutil
from sanji.core import Sanji
from sanji.core import Route
from sanji.model_initiator import ModelInitiator
from sanji.connection.mqtt import Mqtt

logger = logging.getLogger()


class Status(Sanji):

    def init(self, *args, **kwargs):
        path_root = os.path.abspath(os.path.dirname(__file__))
        self.model = ModelInitiator("status", path_root, backup_interval=1)

        # reset flag
        self.model.db["cpuPush"] = 0
        self.model.db["memoryPush"] = 0
        self.model.db["diskPush"] = 0
        self.model.save_db()

        # init thread pool
        self.cpu_thread_pool = []
        self.memory_thread_pool = []
        self.disk_thread_pool = []

    @Route(methods="get", resource="/system/status/cpu")
    def get_cpu(self, message, response):
        if "push" in message.query:
            if message.query["push"] == "true":
                self.model.db["cpuPush"] = 1
                self.model.save_db()

                # start thread
                rc = self.start_thread("cpu")
                if rc is True:
                    return response(data=self.model.db)
                else:
                    return response(code=400,
                                    data={"message": "server push failed"})

        # push query is false, return db
        return response(data=self.model.db)

    @Route(methods="put", resource="/system/status/cpu")
    def put_cpu(self, message, response):
        if hasattr(message, "data") and message.data["cpuPush"] == 0:
            self.model.db["cpuPush"] = message.data["cpuPush"]
            self.model.save_db()

            # kill thread
            rc = self.kill_thread("cpu")
            if rc is True:
                return response(data=self.model.db)
            return response(code=400, data={"message": "cpu status error"})
        return response(code=400, data={"message": "Invaild Input"})

    @Route(methods="get", resource="/system/status/memory")
    def get_memory(self, message, response):
        if "push" in message.query:
            if message.query["push"] == "true":
                self.model.db["memoryPush"] = 1
                self.model.save_db()

                # start thread
                rc = self.start_thread("memory")
                if rc is True:
                    return response(data=self.model.db)
                else:
                    return response(code=400,
                                    data={"message": "server push failed"})

        # push query is false, return db
        return response(data=self.model.db)

    @Route(methods="put", resource="/system/status/memory")
    def put_memory(self, message, response):
        if hasattr(message, "data") and message.data["memoryPush"] == 0:
            self.model.db["memoryPush"] = message.data["memoryPush"]
            self.model.save_db()

            # kill thread
            rc = self.kill_thread("memory")
            if rc is True:
                return response(data=self.model.db)
            return response(code=400, data={"message": "memory status error"})
        return response(code=400, data={"message": "Invaild Input"})

    @Route(methods="get", resource="/system/status/disk")
    def get_disk(self, message, response):
        if "push" in message.query:
            if message.query["push"] == "true":
                self.model.db["diskPush"] = 1
                self.model.save_db()

                # start thread
                rc = self.start_disk_thread()
                if rc is True:
                    return response(data=self.model.db)
                else:
                    return response(code=400,
                                    data={"message": "server push failed"})
        # push query is false, return db
        return response(data=self.model.db)

    @Route(methods="put", resource="/system/status/disk")
    def put_disk(self, message, response):
        if hasattr(message, "data") and message.data["diskPush"] == 0:
            self.model.db["diskPush"] = message.data["diskPush"]
            self.model.save_db()

            # kill thread
            rc = self.kill_disk_thread()
            if rc is True:
                return response(data=self.model.db)
            return response(code=400, data={"message": "disk status error"})
        return response(code=400, data={"message": "Invaild Input"})

    def start_thread(self, fun_type):
        # generate command by fun_type
        if fun_type == "cpu":
            kill_cmd = ("self.kill_thread(\"%s\")" % fun_type)
            thread_cmd = "CpuThread()"
            pool_cmd = "self.cpu_thread_pool.append(t)"
        elif fun_type == "memory":
            kill_cmd = ("self.kill_thread(\"%s\")" % fun_type)
            thread_cmd = "MemoryThread()"
            pool_cmd = "self.memory_thread_pool.append(t)"
        elif fun_type == "disk":
            kill_cmd = ("self.kill_thread(\"%s\")" % fun_type)
            thread_cmd = "DiskThread()"
            pool_cmd = "self.disk_thread_pool.append(t)"
        else:
            return False

        kill_rc = eval(kill_cmd)
        if kill_rc is False:
            return False
        # start call thread to server push
        t = eval(thread_cmd)
        t.start()
        # save to thread pool
        eval(pool_cmd)
        logger.debug("start_%s_thread thread pool: %s"
                     % (fun_type, self.cpu_thread_pool))
        return True

    def kill_thread(self, fun_type):
        print("----------------> in kill_thread:%s" % fun_type)
        # define pool_name by fun_type
        if fun_type == "cpu":
            pool = self.cpu_thread_pool
        elif fun_type == "memory":
            pool = self.memory_thread_pool
        elif fun_type == "disk":
            pool = self.disk_thread_pool
        else:
            return False

        try:
            # kill thread from thread pool
            logger.debug("kill %s thread pool:%s"
                         % (fun_type, pool))
            for thread in pool:
                thread.join()
            # flush thread pool
            pool = []
            return True
        except Exception as e:
            logger.debug("kill cpu thread error: %s" % e)
            return False


class ConvertData:
    # convert size
    @staticmethod
    def human_size(size_bytes):
        if size_bytes == 0:
            return "0 Byte"
        suffixes_table = [("bytes", 0), ("KB", 0), ("MB", 1), ("GB", 2)]
        num = float(size_bytes)
        for suffix, percision in suffixes_table:
            if num < 1024.0:
                break
            num /= 1024.0

        # convert to correct percision
        if percision == 0:
            formatted_size = ("%d" % num)
        else:
            formatted_size = str(round(num, ndigits=percision))
        return "%s %s" % (formatted_size, suffix)

    @staticmethod
    def get_time():
        current_time = time.strftime("%Y/%m/%d %H:%M:%S",
                                     time.localtime(time.time()))
        return current_time


class CpuThread(threading.Thread):

    def __init__(self):
        super(CpuThread, self).__init__()
        self.stoprequest = threading.Event()

    def run(self):
        while not self.stoprequest.isSet():
            # get cpu usage
            usage = self.grep_data()
            logger.debug("cpu usage:%f" % usage)
            # server push data
            # self.publish.event("/remote/sanji/events",
            #                   data={"time": ConvertData.get_time(),
            #                         "usage": usage})
            time.sleep(60)

    def join(self):
        logger.debug("join thread")
        # set event to stop while loop in run
        self.stoprequest.set()
        super(CpuThread, self).join()

    # grep cpu data
    def grep_data(self):
        cpu_usage = psutil.cpu_percent(interval=1)
        logger.debug("cpu usage:%f" % cpu_usage)
        return cpu_usage


class MemoryThread(threading.Thread):

    def __init__(self):
        super(MemoryThread, self).__init__()
        self.stoprequest = threading.Event()

    def run(self):
        while not self.stoprequest.isSet():
            # get cpu usage
            memory_data = self.get_memory_data()
            logger.debug("memory_data:%s" % memory_data)
            # server push data
            # self.publish.event("/remote/sanji/events",
            #                    data=memory_data)
            time.sleep(60)

    def join(self):
        logger.debug("join thread")
        # set event to stop while loop in run
        self.stoprequest.set()
        super(MemoryThread, self).join()

    def get_memory_data(self):
        logger.debug("in get_memory_data")
        mem = psutil.virtual_memory()
        data = {"time": ConvertData.get_time(),
                "total": ConvertData.human_size(mem.total),
                "used": ConvertData.human_size(mem.used),
                "free": ConvertData.human_size(mem.free),
                "usedPercentage": round(((float(mem.used)/mem.total)*100),
                                        ndigits=1)}
        return data


class DiskThread(threading.Thread):

    def __init__(self):
        super(DiskThread, self).__init__()
        self.stoprequest = threading.Event()

    def run(self):
        while not self.stoprequest.isSet():
            # get cpu usage
            disk_data = self.get_disk_data()
            logger.debug("disk_data:%s" % disk_data)
            # server push data
            # self.publish.event("/remote/sanji/events",
            #                   data=disk_data)
            time.sleep(60)

    def join(self):
        logger.debug("join thread")
        # set event to stop while loop in run
        self.stoprequest.set()
        super(DiskThread, self).join()

    def get_disk_data(self):
        logger.debug("in get_disk_data")

        disk = psutil.disk_usage("/")
        data = {"time": ConvertData.get_time(),
                "total": ConvertData.human_size(disk.total),
                "used": ConvertData.human_size(disk.used),
                "free": ConvertData.human_size(disk.free),
                "usedPercentage": disk.percent}
        return data

if __name__ == '__main__':
    FORMAT = '%(asctime)s - %(levelname)s - %(lineno)s - %(message)s'
    logging.basicConfig(level=0, format=FORMAT)
    logger = logging.getLogger("ssh")

    status = Status(connection=Mqtt())
    status.start()
