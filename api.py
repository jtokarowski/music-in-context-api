import json
from flask import Flask, Markup, request, redirect, render_template, jsonify
import requests
from datetime import date
from spotifyClient import data, auth, create
from statisticalAnalysis import stats
import time
import os
from flask_cors import CORS

ENV = os.environ.get('ENV')
SECRET_KEY = ' ' #This doesn't actually get used, but simpleForm needs this to run

#grab date program is being run
td = date.today()
TODAY = td.strftime("%Y%m%d") ##YYYYMMDD
YEAR = td.strftime("%Y") ##YYYY
NICEDATE = td.strftime("%b %d %Y") ##MMM DD YYYY

#creates instance of app
app = Flask(__name__)
CORS(app)
app.config.from_object(__name__)

# Server-side Parameters based on where it's running
if ENV == 'dev':
    CLIENT_SIDE_URL = "http://127.0.0.1"
    PORT = 7000
elif ENV == 'heroku':
    CLIENT_SIDE_URL = "https://musicincontext.herokuapp.com"


@app.route("/data", methods=["POST"])
def response():
    
    #grab the refresh token from the request body + intialize auth class
    spotifyRefreshToken = request.json['refresh_token']
    authorization = auth()
    refreshedSpotifyTokens = authorization.refreshAccessToken(spotifyRefreshToken)
    
    #using access token, initialize data class
    spotifyAccessToken = refreshedSpotifyTokens['access_token']
    spotifyDataRetrieval = data(spotifyAccessToken)

    #TODO checkbox form list the sets we can model the tunnel off of

    # #list of audio features used to fit curve
    spotifyAudioFeatures = ['acousticness','danceability','energy','instrumentalness','liveness','speechiness','valence']
    audioFeaturesColors = ['rgba(102, 255, 153, 1)','rgba(255, 153, 51, 1)','rgba(102, 153, 255, 1)','rgba(204, 0, 0, 1)','rgba(153, 102, 255, 1)','rgba(0, 0, 102, 1)','rgba(115, 115, 115, 1)']
    trackColors = []

    profile = spotifyDataRetrieval.profile()
    userName = profile.get("userName")

    ################################################################
    ###               TUNNEL  BETA                               ###
    ################################################################

    ################################################################
    ##          STEP ZERO - SET TARGETS                           ##
    ################################################################
    DJSET = [{'trackName': 'TheWeekend', 'trackId': '1rkrZxfScVaKmHdwo92Hr7', 'artistNames': ['David Puentez'], 'artistIds': ['4gSsv9FQDyXx0GUkZYha7v'], 'audioFeatures': {'danceability': 0.805, 'energy': 0.665, 'key': 6, 'loudness': -4.161, 'mode': 1, 'speechiness': 0.0433, 'acousticness': 0.663, 'instrumentalness': 1.3e-06, 'liveness': 0.135, 'valence': 0.77, 'tempo': 125.935, 'type': 'audio_features', 'id': '1rkrZxfScVaKmHdwo92Hr7', 'uri': 'spotify:track:1rkrZxfScVaKmHdwo92Hr7', 'track_href': 'https://api.spotify.com/v1/tracks/1rkrZxfScVaKmHdwo92Hr7', 'analysis_url': 'https://api.spotify.com/v1/audio-analysis/1rkrZxfScVaKmHdwo92Hr7', 'duration_ms': 139048, 'time_signature': 4}, 'genres': ['progressive electro house']}, {'trackName': 'StringsOfLife-AtfcRemix', 'trackId': '0RQ2U4kyyRpa4GhaK5WZPg', 'artistNames': ['Kanu', 'Jude & Frank', 'ATFC'], 'artistIds': ['7qGg5f7GRoEEDsjhetcseQ', '7rUJV3QhhZJVRucw5BK09x', '04L4Y7Hkc1fULKhFbTnSSs'], 'audioFeatures': {'danceability': 0.636, 'energy': 0.864, 'key': 1, 'loudness': -6.365, 'mode': 1, 'speechiness': 0.0455, 'acousticness': 0.011, 'instrumentalness': 0.454, 'liveness': 0.0484, 'valence': 0.755, 'tempo': 124.984, 'type': 'audio_features', 'id': '0RQ2U4kyyRpa4GhaK5WZPg', 'uri': 'spotify:track:0RQ2U4kyyRpa4GhaK5WZPg', 'track_href': 'https://api.spotify.com/v1/tracks/0RQ2U4kyyRpa4GhaK5WZPg', 'analysis_url': 'https://api.spotify.com/v1/audio-analysis/0RQ2U4kyyRpa4GhaK5WZPg', 'duration_ms': 163322, 'time_signature': 4}, 'genres': ['funky tech house', 'italian tech house', 'chicago house', 'deep house', 'disco house', 'funky tech house', 'house', 'tech house', 'tribal house', 'vocal house']}, {'trackName': 'Dvncefloor', 'trackId': '6lBZpeJ5knvYhsMQArHtOX', 'artistNames': ['Cheyenne Giles', 'Knock2'], 'artistIds': ['2FoyDZAnGzikijRdXrocmj', '6mmSS7itNWKbapgG2eZbIg'], 'audioFeatures': {'danceability': 0.829, 'energy': 0.93, 'key': 10, 'loudness': -3.998, 'mode': 0, 'speechiness': 0.156, 'acousticness': 0.000389, 'instrumentalness': 0.0136, 'liveness': 0.054, 'valence': 0.48, 'tempo': 126.025, 'type': 'audio_features', 'id': '6lBZpeJ5knvYhsMQArHtOX', 'uri': 'spotify:track:6lBZpeJ5knvYhsMQArHtOX', 'track_href': 'https://api.spotify.com/v1/tracks/6lBZpeJ5knvYhsMQArHtOX', 'analysis_url': 'https://api.spotify.com/v1/audio-analysis/6lBZpeJ5knvYhsMQArHtOX', 'duration_ms': 152797, 'time_signature': 4}, 'genres': []}, {'trackName': 'HitTheFlow', 'trackId': '7r2VuLH3NqOu0bXF976eFY', 'artistNames': ['Landis'], 'artistIds': ['7bSDGumYzI7Cehekr534Xn'], 'audioFeatures': {'danceability': 0.817, 'energy': 0.987, 'key': 6, 'loudness': -3.344, 'mode': 0, 'speechiness': 0.231, 'acousticness': 0.0038, 'instrumentalness': 0.0432, 'liveness': 0.33, 'valence': 0.643, 'tempo': 128.002, 'type': 'audio_features', 'id': '7r2VuLH3NqOu0bXF976eFY', 'uri': 'spotify:track:7r2VuLH3NqOu0bXF976eFY', 'track_href': 'https://api.spotify.com/v1/tracks/7r2VuLH3NqOu0bXF976eFY', 'analysis_url': 'https://api.spotify.com/v1/audio-analysis/7r2VuLH3NqOu0bXF976eFY', 'duration_ms': 151875, 'time_signature': 4}, 'genres': ['pop edm']}]
   
    #initialize mapreduce lists - aligned with target tracks
    minimumDistances = [999999] * len(DJSET)
    minimumDistanceTracks = ["None"] * len(DJSET)
    minimumDistanceTrackIDs = ["None"] * len(DJSET)
    
    newSetTargets = []

    skipFeatures = ['liveness']

    #set max distance per attribute we are willing to use
    bound = 0.2
    
    trackIndex = 0
    for track in DJSET:
        trackTargets = {}
        for audioFeature in spotifyAudioFeatures:
            #store the features in same format for easy ED calc later
            trackTargets['audioFeatures'] =  track['audioFeatures']

            #set targets + min/max
            key = "target_{}".format(audioFeature)
            trackTargets[key] = track['audioFeatures'][audioFeature]
                
            minKey = "min_{}".format(audioFeature)
            maxKey = "max_{}".format(audioFeature)
            trackTargets[minKey] = max(track['audioFeatures'][audioFeature] - bound,0)
            trackTargets[maxKey] = min(track['audioFeatures'][audioFeature] + bound,1)

        trackTargets['trackIndex'] = trackIndex
        newSetTargets.append(trackTargets)
        trackIndex +=1

    print("Completed target setup")

    ################################################################
    ##    STEP ONE - BUILD POOL OF SUGGESTED TRACKS + MAP         ##
    ################################################################

    #build up list of user top artists
    topListenType = 'artists'
    userTopArtists = []
    #userTopArtists.extend(spotifyDataRetrieval.getMyTop(topType=topListenType, term='short_term', limit=1))
    userTopArtists.extend(spotifyDataRetrieval.getMyTop(topType=topListenType, term='medium_term', limit=1))
    userTopArtists.extend(spotifyDataRetrieval.getMyTop(topType=topListenType, term='long_term', limit=1))
    #remove dupes
    userTopArtists = list(set(userTopArtists))
    print("Loaded {} user top artists".format(len(userTopArtists)))

    # Build up a large pool of options by grabbing suggestions for each
    # of top artists, target 0 and target 1 to get almost all of pool
    cleanMasterTrackPool = []
    cleanMasterTrackPoolIDs = []
    for artist in userTopArtists:  
        recommendedTracks = spotifyDataRetrieval.getRecommendations(limit = 20, seed_artists = artist)
        
        #continue if we don't get anything back
        if len(recommendedTracks) == 0 or recommendedTracks == None:
            continue

        cleanRecommendations = spotifyDataRetrieval.cleanTrackData(recommendedTracks)
        cleanRecommendationsWithFeatures = spotifyDataRetrieval.getAudioFeatures(cleanRecommendations)
        
        trackPoolAdditions = 0
        for cleanTrack in cleanRecommendationsWithFeatures:
            #check if it will dupe
            if cleanTrack['trackID'] not in cleanMasterTrackPoolIDs:
                #calculate distance to each target
                cleanTrack['euclideanDistances'] = []
                cleanTrack['isUsed'] = False
                arrayIndex = 0
                for target in newSetTargets:
                    euclideanDistance = spotifyDataRetrieval.calculateEuclideanDistance(cleanTrack, target, spotifyAudioFeatures, "absValue")
                    #build a list for each suggested track to each target
                    cleanTrack['euclideanDistances'].append(euclideanDistance)
                    #check vs the current closest match
                    if euclideanDistance < minimumDistances[arrayIndex]:
                        #make sure we don't dupe a track in the new set
                        if cleanTrack['trackID'] not in minimumDistanceTrackIDs:
                            minimumDistances[arrayIndex] = euclideanDistance
                            minimumDistanceTracks[arrayIndex] = cleanTrack
                            minimumDistanceTrackIDs[arrayIndex] = cleanTrack['trackID']
                    
                    #check against next target
                    arrayIndex += 1

                trackPoolAdditions += 1
                cleanMasterTrackPool.append(cleanTrack)
                cleanMasterTrackPoolIDs.append(cleanTrack['trackID'])
        print("Added {} tracks to recommendations pool".format(trackPoolAdditions))

    print("Loaded {} unique track recommendations".format(len(cleanMasterTrackPoolIDs)))

    ################################################################
    ##           STEP TWO SEND SET TO FRONTEND                    ##
    ################################################################

    #declare framework for outgoing data
    outgoingData = {
        #line chart data
        'dataByAttribute':{
            'datasets':[]
        },
        #radar chart data
        #TODO bug caused by FE looking for this with lowercase, should camelcase it
        'databyTrack':{
            'labels':spotifyAudioFeatures,
            'datasets':[]
        }}

    #create a dict of lists to store line chart data
    dataOrganizedByAttribute = {}
    for attribute in spotifyAudioFeatures:
        dataOrganizedByAttribute[attribute] = []
    dataOrganizedByAttribute['trackName'] = []

    #reformat data into outgoing structure
    for track in minimumDistanceTracks:
        trackDataForRadar = {}

        trackDataForRadar['label'] = track['trackName']
        dataOrganizedByAttribute['trackName'].append(track['trackName'])

        #TODO make colors beautiful
        trackDataForRadar['borderColor'] = 'rgba(25, 25, 25, 1)'
        trackDataForRadar['fill'] = 'false'
        
        trackDataForRadar['data'] = []
        for audioFeature in spotifyAudioFeatures:
            trackDataForRadar['data'].append(track['audioFeatures'][audioFeature])
            dataOrganizedByAttribute[audioFeature].append(track['audioFeatures'][audioFeature])
        outgoingData['databyTrack']['datasets'].append(trackDataForRadar)

    #form the data by attribute (for line chart)
    outgoingData['dataByAttribute']['labels'] = dataOrganizedByAttribute['trackName']
    colorIndex = 0
    for audioFeature in spotifyAudioFeatures:
        dataForLineChart = {}
        dataForLineChart['label'] = audioFeature
        # loop thru colors for line graph
        dataForLineChart['borderColor'] = audioFeaturesColors[colorIndex]
        colorIndex += 1

        dataForLineChart['fill'] = 'false'
        dataForLineChart['data'] = dataOrganizedByAttribute[audioFeature]

        outgoingData['dataByAttribute']['datasets'].append(dataForLineChart)

    return json.dumps(outgoingData)




#instantiate app
if __name__ == "__main__":
    if ENV == 'heroku':
        app.run(debug=False)
    else:
        app.run(debug=True, port=PORT)