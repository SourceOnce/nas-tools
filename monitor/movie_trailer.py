import os
import shutil

from tmdbv3api import TMDb, Movie
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer
from xml.dom.minidom import parse

from functions import get_dir_files_by_name, system_exec_command
from scheduler.hot_trailer import transfer_trailers

import log
import settings

# 全局设置
logger = log.Logger("monitor").logger

movie_flag = settings.get("monitor.movie_flag") == "ON" or False
monpath = settings.get("monitor.movie_monpath")
youtube_dl_cmd = settings.get("youtobe.youtube_dl_cmd")
hottrailer_path = settings.get("youtobe.hottrailer_path")

handler_files = []
tmdb = TMDb()
tmdb.api_key = settings.get('rmt.rmt_tmdbkey')
tmdb.language = 'en-US'
tmdb.debug = True
movie = Movie()


# 解析nfoXML文件，午到tmdbid
def get_movie_info_from_nfo(in_path):
    try:
        domTree = parse(in_path)
        rootNode = domTree.documentElement
        tmdbid = rootNode.getElementsByTagName("tmdbid")[0].firstChild.data
        title = rootNode.getElementsByTagName("title")[0].firstChild.data
        year = rootNode.getElementsByTagName("releasedate")[0].firstChild.data[0:4]
        return tmdbid, title, year
    except Exception as err:
        logger.error("解析nfo文件出错：" + str(err))
        return None, None, None


# 下载预告片
def download_movie_trailer(in_path):
    exists_trailers = get_dir_files_by_name(in_path, "-trailer.")
    if len(exists_trailers) > 0:
        logger.error("电影目录已存在预告片，跳过...")
        return
    nfo_files = get_dir_files_by_name(in_path, ".nfo")
    if len(nfo_files) == 0:
        logger.error("nfo文件不存在，跳过...")
        return
    movie_id, movie_title, movie_year = get_movie_info_from_nfo(nfo_files[0])
    if not movie_id or not movie_title or not movie_year:
        return

    trailer_dir = hottrailer_path + "/" + movie_title + " (" + movie_year + ")"
    file_path = trailer_dir + "/" + movie_title + " (" + movie_year + ").%(ext)s"
    # 开始下载
    try:
        movie_videos = movie.videos(movie_id)
    except Exception as err:
        logger.error("错误：" + str(err))
        return
    logger.info("预告片总数：" + str(len(movie_videos)))
    if len(movie_videos) > 0:
        logger.info("电影：" + str(movie_id) + " - " + movie_title)
        succ_flag = False
        for video in movie_videos:
            trailer_key = video.key
            logger.info(">下载：" + trailer_key)
            exec_cmd = youtube_dl_cmd.replace("$PATH", file_path).replace("$KEY", trailer_key)
            logger.info(">开始执行命令：" + exec_cmd)
            # 获取命令结果
            result_err, result_out = system_exec_command(exec_cmd, 180)
            if result_err:
                logger.error(">错误信息：" + result_err)
            if result_out:
                logger.info(">执行结果：" + result_out)
            if result_err != "":
                succ_flag = False
                continue
            else:
                succ_flag = True
                break
        if not succ_flag:
            shutil.rmtree(trailer_dir, ignore_errors=True)
        # 转移
        transfer_trailers(trailer_dir)
    else:
        logger.info(movie_title + " 未检索到预告片")


# 处理文件夹
def dir_change_handler(event, text):
    event_path = event.src_path
    if event.is_directory:  # 文件改变都会触发文件夹变化
        try:
            logger.info(text + "了文件夹: %s " % event_path)
            if event_path == monpath:
                return
            name = os.path.basename(event_path)
            logger.info("名称：" + name)
            if event_path not in handler_files:
                handler_files.append(event_path)
                logger.info("开始处理：" + event_path)
                # 下载预告片
                download_movie_trailer(event_path)
                logger.info(event_path + "处理成功！")
            else:
                logger.error("已处理过：" + name)
        except Exception as e:
            logger.error("发生错误：" + str(e))


# 监听文件夹
class FileMonitorHandler(FileSystemEventHandler):
    def __init__(self, **kwargs):
        super(FileMonitorHandler, self).__init__(**kwargs)
        # 监控目录 目录下面以device_id为目录存放各自的图片
        self._watch_path = monpath

    # 重写文件创建函数，文件创建都会触发文件夹变化
    def on_created(self, event):
        dir_change_handler(event, "创建")

    def on_moved(self, event):
        dir_change_handler(event, "移动")

    def on_modified(self, event):
        dir_change_handler(event, "修改")


def run_movie_trailer():
    if os.path.exists(monpath) and movie_flag:
        event_handler = FileMonitorHandler()
        observer = Observer()
        observer.schedule(event_handler, path=monpath, recursive=True)  # recursive递归的
        observer.setDaemon(False)
        observer.start()
        logger.info("monitor.movie_trailer启动...")
    else:
        logger.error(monpath + "目录不存在！")


# 下载电影预告片
def movie_trailer_all():
    logger.info("开始检索和下载电影预告片！")
    movie_dir_list = os.listdir(monpath)
    for movie_dir in movie_dir_list:
        movie_dir = os.path.join(monpath, movie_dir)
        if os.path.isdir(movie_dir):
            download_movie_trailer(movie_dir)
    logger.info("电影预告片下载任务完成！")


if __name__ == "__main__":
    movie_trailer_all()