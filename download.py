# This Python file uses the following encoding: utf-8
from __future__ import unicode_literals
from argparse import ArgumentParser
import os
import json
import shutil
import socket
import unicodedata
import tmdbsimple as tmdb
# import youtube_dl
import yt_dlp
import urllib
import sys
import requests

# Python 3.0 and later
try:
    from configparser import *
    from urllib.request import *
    from urllib.error import *

# Python 2.7
except ImportError:
    from ConfigParser import *
    from urllib2 import *

# Arguments
def getArguments():
    parser = ArgumentParser(description='Download a movie trailer from Apple or YouTube')
    parser.add_argument("-d", "--directory", dest="directory", help="Full path of directory to copy downloaded trailer", metavar="DIRECTORY")
    parser.add_argument("-f", "--file", dest="file", help="Full path of movie file", metavar="FILE")
    parser.add_argument("-t", "--title", dest="title", help="Title of movie", metavar="TITLE")
    parser.add_argument("-y", "--year", dest="year", help="Release year of movie", metavar="YEAR")
    args = parser.parse_args()
    return {
        'directory': args.directory,
        'file': args.file,
        'title': args.title,
        'year': args.year
    }

# Settings
def getSettings():
    config = ConfigParser()
    config.read(os.path.split(os.path.abspath(__file__))[0]+'/settings.ini')
    return {
        'api_key': config.get('DEFAULT', 'tmdb_api_key'),
        'region': config.get('DEFAULT', 'region'),
        'lang': config.get('DEFAULT', 'lang'),
        'resolution': config.get('DEFAULT', 'resolution'),
        'max_resolution': config.get('DEFAULT', 'max_resolution'),
        'min_resolution': config.get('DEFAULT', 'min_resolution'),
        'ffmpeg_path': config.get('DEFAULT', 'ffmpeg_path')
    }

# Remove special characters
def removeSpecialChars(query):
    return "".join([ch for ch in query if ch.isalnum() or ch.isspace()])

# Match titles
def matchTitle(title):
    return unicodedata.normalize('NFKD', removeSpecialChars(title).replace('/', '').replace('\\', '').replace('-', '').replace(':', '').replace('*', '').replace('?', '').replace('"', '').replace("'", '').replace('<', '').replace('>', '').replace('|', '').replace('.', '').replace('+', '').replace(' ', '').lower()).encode('ASCII', 'ignore')

# get final Trailer location
def getFileLocation(subFolder, title, year):
    if subFolder:
        filename = "Trailers/" + title+' ('+year+').mp4'
    else:
        filename = title+' ('+year+')-trailer.mp4'
    return filename

# Load json from url
def loadJson(url):
    response = urlopen(url)
    str_response = response.read().decode('utf-8')
    return json.loads(str_response)

# Get file urls
def getUrls(page_url, res):
    urls = []
    film_data = loadJson(page_url + '/data/page.json')
    title = film_data['page']['movie_title']
    apple_size = mapRes(res)

    for clip in film_data['clips']:
        video_type = clip['title']
        if apple_size in clip['versions']['enus']['sizes']:
            file_info = clip['versions']['enus']['sizes'][apple_size]
            file_url = convertUrl(file_info['src'], res)
            video_type = video_type.lower()
            if (video_type.startswith('trailer')):
                url_info = {
                    'res': res,
                    'title': title,
                    'type': video_type,
                    'url': file_url,
                }
                urls.append(url_info)

    final = []
    length = len(urls)

    if length > 1:
        final.append(urls[length-1])
        return final
    else:
        return urls

# Map resolution
def mapRes(res):
    res_mapping = {'480': u'sd', '720': u'hd720', '1080': u'hd1080'}
    if res not in res_mapping:
        res_string = ', '.join(res_mapping.keys())
        raise ValueError("Invalid resolution. Valid values: %s" % res_string)
    return res_mapping[res]

# Convert source url to file url
def convertUrl(src_url, res):
    src_ending = "_%sp.mov" % res
    file_ending = "_h%sp.mov" % res
    return src_url.replace(src_ending, file_ending)

# Download URL contents to a file with progress
def download(url, filename):
    with open(filename, 'wb') as f:
        response = requests.get(url, headers = {'User-Agent': 'Quick_time/7.6.2'}, stream=True)
        total = response.headers.get('content-length')

        if total is None:
            f.write(response.content)
        else:
            downloaded = 0
            total = int(total)
            for data in response.iter_content(chunk_size=max(int(total / 1000), 1024 * 1024)):
                downloaded += len(data)
                f.write(data)
                done = int(50 * downloaded / total)
                sys.stdout.write('\r[{}{}]'.format('█' * done, '.' * (50 - done)))
                sys.stdout.flush()
    sys.stdout.write('\n')

# Move to final locations
def moveIntoPlace(source, target):
    try:
        # Move downloaded trailer to directory
        shutil.move(source, target)
        if not os.path.exists(target):
            print('Problem moving trailer to ' + target)
        return
    except shutil.Error as error:
        print('Error moving trailer: ' + error.message)
        return

# Download the file
def downloadFile(url, destdir, filename):
    download(url, '/tmp/' + filename)
    moveIntoPlace('/tmp/' + filename, destdir + '/' + filename)

# Download from Apple
def appleDownload(page_url, res, destdir, filename):
    trailer_urls = getUrls(page_url, res)
    for trailer_url in trailer_urls:
        downloadFile(trailer_url['url'], destdir, filename)
        return filename

# Search Apple
def searchApple(query):
    query = removeSpecialChars(query)
    query = query.replace(' ', '+')
    search_url = 'https://trailers.apple.com/trailers/home/scripts/quickfind.php?q='+query
    return loadJson(search_url)

# Search TMDB
def searchTMDB(query, api_key):
    query = removeSpecialChars(query)
    tmdb.API_KEY = api_key
    search = tmdb.Search()
    return search.movie(query=query)

# Search TMDB for videos
def videosTMDB(id, lang, region, api_key):
    tmdb.API_KEY = api_key
    movie = tmdb.Movies(id)
    return movie.videos(language=lang+'-'+region)

# Download file from YouTube
def youtubeDownload(video, min_resolution, max_resolution, title, year, directory, ffmpeg_path, subFolder):
    filename = getFileLocation(subFolder, title, year)
    options = {
        'format': 'bestvideo[ext=mp4][height<='+max_resolution+']+bestaudio[ext=m4a]',
        'default_search': 'ytsearch1:',
        'restrict_filenames': 'TRUE',
        'prefer_ffmpeg': 'TRUE',
        'ffmpeg_location': ffmpeg_path,
        'quiet': 'TRUE',
        'ignore_warnings': 'TRUE',
        'ignore_errors': 'TRUE',
        'no_playlist': 'TRUE',
        'outtmpl': '/tmp/' + filename
    }

    try:
        # Download
        with yt_dlp.YoutubeDL(options) as youtube:
            file = youtube.extract_info(video, download=True)
        # Move downloaded trailer to directory
        if not os.path.exists(directory):
            os.makedirs(directory)
        moveIntoPlace('/tmp/' + filename, directory + '/' + filename)
        return file
    except:
        return False

# Main
def main():
    # Arguments
    arguments = getArguments()

    # Settings
    settings = getSettings()

    # Make sure a movie directory or file, title, and year was passed
    if (arguments['directory'] != None or arguments['file'] != None) and arguments['title'] != None and arguments['year'] != None:

        # If directory argument is not set, get directory from file
        if arguments['directory'] == None and arguments['file'] != None:
            arguments['directory'] = os.path.abspath(os.path.dirname(arguments['file']))

        try:
            directory = arguments['directory'].decode('utf-8')
            title = arguments['title'].decode('utf-8')
            year = arguments['year'].decode('utf-8')
        except AttributeError:
            directory = arguments['directory']
            title = arguments['title']
            year = arguments['year']
        subFolder = False
        
        # Make sure trailer file doesn't already exist in the directory
        if not os.path.exists(directory + '/' + getFileLocation(subFolder, title, year)):

            # Download status
            downloaded = False

            # Search Apple for trailer
            if not downloaded:
                search = searchApple(title)

                # Iterate over search results
                for result in search['results']:

                    # Filter by year and title
                    if year.lower() in result['releasedate'].lower() and matchTitle(title) == matchTitle(result['title']):

                        file = appleDownload('https://trailers.apple.com/'+result['location'], settings['resolution'], directory, getFileLocation(subFolder, title, year))

                        # Update downloaded status
                        if file:
                            print('Apple download successful.')
                            downloaded = True
                            break

            # Search YouTube for trailer
            if not downloaded:
                search = searchTMDB(title, settings['api_key'])

                # Iterate over search results
                for result in search['results']:

                    # Filter by year and title
                    if year.lower() in result['release_date'].lower() and matchTitle(title) == matchTitle(result['title']):

                        # Find trailers for movie
                        videos = videosTMDB(result['id'], settings['lang'], settings['region'], settings['api_key'])

                        for item in videos['results']:
                            if 'Trailer' in item['type'] and int(item['size']) >= int(settings['min_resolution']):
                                video = 'https://www.youtube.com/watch?v='+item['key']

                                # Download trailer from YouTube
                                file = youtubeDownload(video, settings['min_resolution'], settings['max_resolution'], title, year, directory, settings['ffmpeg_path'], subFolder)

                                # Update downloaded status
                                if file:
                                    print('Youtube download successful.')
                                    downloaded = True
                                    break

#                         break

            # Still not found
            if not downloaded:
                print('Trailer not found on either Apple or Youtube.')
        else:

            print('\033[91mERROR:\033[0m the trailer already exists in the selected directory')

    else:

        print('\033[91mERROR:\033[0m you must pass a movie directory or file, title, and year to the script')

# Run
if __name__ == '__main__':
    main()
