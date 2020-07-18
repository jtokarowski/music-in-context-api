import json
from flask import Flask, Markup, request, redirect, render_template, jsonify
import requests
from datetime import date
from spotifyClient import data, auth, create
from statisticalAnalysis import stats
import time
import os
from flask_cors import CORS
from pymongo import MongoClient
from collections import Counter

ENV = os.environ.get('ENV')

# #list of audio features used to fit curve, shared across modes
spotifyAudioFeatures = ['acousticness','danceability','energy','instrumentalness','liveness','speechiness','valence']

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
    PORT = 7000
    client = MongoClient('localhost', 27017)
    db = client.musicInContext
    BACKEND_URL = "http://127.0.0.1:7000"
elif ENV == 'heroku':
    MONGODB_URI=os.environ.get('MONGODB_URI')
    client = MongoClient(MONGODB_URI)
    db = client[os.environ.get('MONGODB_DBNAME')]
    BACKEND_URL = "https://music-in-context-backend.herokuapp.com"

def retrieveUserContext(spotifyRefreshToken):

    #shared function to retrieve user context from DB or send request to create it
    authorization = auth()
    refreshedSpotifyTokens = authorization.refreshAccessToken(spotifyRefreshToken)
    spotifyAccessToken = refreshedSpotifyTokens['access_token']
    spotifyDataRetrieval = data(spotifyAccessToken)
    profile = spotifyDataRetrieval.profile()
    userName = profile.get("userName")

    #check if we have user in the DB, else build their context
    userContextCollection = db['userContext']
    cursor = userContextCollection.find({})

    thisUserContext = None
    for userContext in cursor:
        if userName == userContext['userName']:
            print('found the user')
            thisUserContext = userContext

    if thisUserContext is None:
        print('could not find user. getting context now.')
        postURL = '{}/usercontext'.format(BACKEND_URL)
        postRequest = requests.post(postURL, json={'refresh_token': spotifyRefreshToken})        
        print('done creating user context. pulling in now')
        cursor = userContextCollection.find({})
        for userContext in cursor:
            if userName == userContext['userName']:
                print('found the user')
                thisUserContext = userContext

    return thisUserContext

@app.route("/")
def pingroute():
    return "OK"

@app.route("/commitplaylist", methods=['POST'])
def commitplaylist():

    spotifyRefreshToken = request.json['refresh_token']
    mode = request.json['mode']
    authorization = auth()
    refreshedSpotifyTokens = authorization.refreshAccessToken(spotifyRefreshToken)
    spotifyAccessToken = refreshedSpotifyTokens['access_token']
    spotifyDataRetrieval = data(spotifyAccessToken)
    spotifyCreate = create(spotifyAccessToken)
    profile = spotifyDataRetrieval.profile()
    userName = profile.get("userName")

    thisUserContext = retrieveUserContext(spotifyRefreshToken)

    if mode == 'tunnel':
        #just commit the one playlist, stored in user context
        print('comitting to spotify')
        trackURIs = []
        for track in thisUserContext['currentSet']:
            trackURIs.append(spotifyDataRetrieval.idToURI("track",track['trackID']))

        newPlaylistInfo = spotifyCreate.newPlaylist(userName, "+| Music in Context- tailored deep house set |+", "Inspired by Nora en Pure | Created by Jtokarowski 2020") #TODO pull in genre for set name
        newPlaylistID = spotifyDataRetrieval.URItoID(newPlaylistInfo['uri'])
        
        n = 50 #spotify playlist addition limit
        for i in range(0, len(trackURIs), n):  
            playlistTracksSegment = trackURIs[i:i + n]
            spotifyCreate.addTracks(newPlaylistID, playlistTracksSegment)

        return "OK - committed playlist to spotify"
    
    else: #TODO make this flexible to support cluster method
        return "Error- this mode not supported"



    

@app.route("/changeset", methods=['POST'])
def changeset():

    spotifyRefreshToken = request.json['refresh_token']
    mode = request.json['mode']
    authorization = auth()
    refreshedSpotifyTokens = authorization.refreshAccessToken(spotifyRefreshToken)
    spotifyAccessToken = refreshedSpotifyTokens['access_token']
    spotifyDataRetrieval = data(spotifyAccessToken)
    profile = spotifyDataRetrieval.profile()
    userName = profile.get("userName")

    thisUserContext = retrieveUserContext(spotifyRefreshToken)

    #retrieve previous set from request body and context object
    discardedTracks = thisUserContext['discardedTracks']
    previousTrackList = request.json['previousTrackList']
    usedTrackIDs = request.json['previousTrackIDs']
    print(usedTrackIDs)
    #TODO this

    #grab the pool of recs from spotify
    recommendedTrackPlaylistID = thisUserContext['recommendedTracks']
    recommendedTracks = spotifyDataRetrieval.getPlaylistTracks(spotifyDataRetrieval.idToURI("playlist", recommendedTrackPlaylistID))
    cleanRecommendations = spotifyDataRetrieval.cleanTrackData(recommendedTracks)
    cleanRecommendationsWithFeatures = spotifyDataRetrieval.getAudioFeatures(cleanRecommendations)

    #for each track in previous set, check if it needs to be refreshed
    previousSetIndex = 0
    for previousTrack in previousTrackList:
        if previousTrack['audioFeatures']['shouldChange'] == 1:
            discardedTracks.append(previousTrack['trackID']) #so we don't use it elsewhere
            minED = 9999999999
            
            #TODO make this more efficient with mapreduce, also fix the spaghetti code incrementor
            #loop through the pool of recommendations to find best fit
            stagedTrack = None
            for newTrack in cleanRecommendationsWithFeatures:
                newTrack['audioFeatures']['shouldChange'] = 0
                if newTrack['trackID'] in usedTrackIDs:
                    continue
                elif newTrack['trackID'] in discardedTracks:
                    continue
                else:
                    euclideanDistance = spotifyDataRetrieval.calculateEuclideanDistance(newTrack, previousTrack, spotifyAudioFeatures, "absValue")
                    if euclideanDistance < minED:
                        #newTrack['isUsed'] = True #TODO this blocks track from being used elsewhere
                        minED = euclideanDistance
                        #stage the new track
                        stagedTrack = newTrack

                        #TODO remove previous track from used, unless it's in discarded
                        #Need to add shouldChange songs to discard list
                        #currentlyInUse can be an indicator, so we don't dupe a track in a set, but can reuse it if it hasn't been sent to FE before
            #swap the new track in
            previousTrackList[previousSetIndex] = stagedTrack
            usedTrackIDs[previousSetIndex] = stagedTrack['trackID']

        previousSetIndex+=1

    #update currentSet field
    userContextCollection = db['userContext']
    userContextCollection.update_one({'userName': userName}, {"$set": {"currentSet": previousTrackList}})
    userContextCollection.update_one({'userName': userName}, {"$set": {"discardedTracks": discardedTracks}})

    return json.dumps({
        "newTracks": previousTrackList,
        "trackIDs": usedTrackIDs
    })

@app.route("/usercontext", methods=["POST"])
def buildUserContext():

    print('arrived in build user context')

    spotifyRefreshToken = request.json['refresh_token']
    #mode = request.json['mode']
    #using access token, initialize data class
    authorization = auth()
    refreshedSpotifyTokens = authorization.refreshAccessToken(spotifyRefreshToken)
    spotifyAccessToken = refreshedSpotifyTokens['access_token']
    spotifyDataRetrieval = data(spotifyAccessToken)
    profile = spotifyDataRetrieval.profile()
    userName = profile.get("userName")

    #check if we have user in the DB, else build their context
    userContextCollection = db['userContext']
    cursor = userContextCollection.find({})

    for userContext in cursor:
        if userName == userContext['userName']:
            print('found the user')
            #TODO check when it was last updated, update as needed
            #TODO use mongo search rather than a loop
            return 'OK'
    
    #assuming we don't find the user, build the context
    #get all user playlists
    allUserPlaylists = spotifyDataRetrieval.currentUserPlaylists()
    playlistObjects = []
    for playlist in allUserPlaylists:
        playlistObjects.append({
            'playlistID':spotifyDataRetrieval.URItoID(playlist['uri']),
            'playlistName': playlist['playlistName']
        })

    #get top user artists
    shortTermTopArtists = spotifyDataRetrieval.getMyTop(topType='artists', term='short_term', limit=10)
    mediumTermTopArtists = spotifyDataRetrieval.getMyTop(topType='artists', term='medium_term', limit=10)
    longTermTopArtists = spotifyDataRetrieval.getMyTop(topType='artists', term='long_term', limit=10)

    #combine and remove dupes
    userTopArtists = shortTermTopArtists
    userTopArtists.extend(mediumTermTopArtists)
    userTopArtists.extend(longTermTopArtists)
    userTopArtists = list(set(userTopArtists))

    #build a pool of recommendations
    recommendedTrackURIs = []
    for artist in userTopArtists:  
        recommendedTracks = spotifyDataRetrieval.getRecommendations(limit = 20, seed_artists = artist)
        if len(recommendedTracks) == 0 or recommendedTracks == None:
            continue
        else:
            for track in recommendedTracks:
                if track['uri'] not in recommendedTrackURIs:
                    recommendedTrackURIs.append(track['uri'])
    
    #print("Loaded {} unique track recommendations".format(len(recommendedTrackURIs)))
    #store the pool in spotify and store the playlist ID
    spotifyCreate = create(spotifyAccessToken)
    newPlaylistInfo = spotifyCreate.newPlaylist(userName, "+| music in context - record box |+", 'Pool of recommended tracks | Music in Context')
    newPlaylistID = spotifyDataRetrieval.URItoID(newPlaylistInfo['uri'])
    
    if len(recommendedTrackURIs)>0:
        n = 50 #spotify playlist addition limit
        for i in range(0, len(recommendedTrackURIs), n):  
            spotifyCreate.addTracks(newPlaylistID, recommendedTrackURIs[i:i + n])

    userContext = {
        'userName':userName,
        'playlists': playlistObjects,
        'topArtists':{
            'shortTerm': shortTermTopArtists,
            'mediumTerm': mediumTermTopArtists,
            'longTerm': longTermTopArtists
        },
        'recommendedTracks': newPlaylistID,
        'discardedTracks':[],
        'lastUpdated': TODAY,
        'currentSet': "N/A",
        'filteredTrackPool': [],
        'clusters':[]
    }

    pymongoResponse = userContextCollection.insert_one(userContext)
    print(pymongoResponse)

    return 'OK'

@app.route("/clustertracks", methods=["POST"])
def clustertracks():

    #this method will run user track recs thru kmeans clustering
    #then propose different styles to user for their set
    spotifyRefreshToken = request.json['refresh_token']
    mode = request.json['mode']
    authorization = auth()
    refreshedSpotifyTokens = authorization.refreshAccessToken(spotifyRefreshToken)
    spotifyAccessToken = refreshedSpotifyTokens['access_token']
    spotifyDataRetrieval = data(spotifyAccessToken)
    profile = spotifyDataRetrieval.profile()
    userName = profile.get("userName")

    thisUserContext = retrieveUserContext(spotifyRefreshToken)

    if mode == "tunnel":
        print("Clustering tracks in user recommendation pool")
        playlistIDs =  [thisUserContext['recommendedTracks']]
    else:
        return "Error- This mode is not supported"
        #TODO make this method accept list of playlists to support OG cluster mode

    masterTrackList = []
    for playlistID in playlistIDs:
        tracks = spotifyDataRetrieval.getPlaylistTracks(spotifyDataRetrieval.idToURI("playlist", playlistID))
        masterTrackList.extend(tracks)

    cleanedMasterTrackList = spotifyDataRetrieval.cleanTrackData(masterTrackList)
    masterTrackListWithFeatures = spotifyDataRetrieval.getAudioFeatures(cleanedMasterTrackList)

        #set up kmeans, check how many songs
    if len(masterTrackListWithFeatures)<5:
        clusters = len(masterTrackListWithFeatures)
    else:
        clusters = 5 #TODO make this dynamic

    #send tracklist to statistics class for k-means calcs
    statistics = stats(masterTrackListWithFeatures)
    statistics.kMeans(spotifyAudioFeatures, clusters)
    dataframeWithClusters = statistics.df
    clusterCenterCoordinates = statistics.centers

    clusterObjects = []
    clusterIndex = 0
    #filter dataframe to one cluster
    for cluster in clusterCenterCoordinates:
        dataframeFilteredToSingleCluster = dataframeWithClusters.loc[dataframeWithClusters['kMeansAssignment'] == clusterIndex]

        #create cluster info object
        clusterObject = {}
        clusterObject['clusterNumber'] = clusterIndex
        clusterObject['audioFeatureCoordinates'] = {}
        
        #grab the genres and artists in the cluster, flatten
        genres = dataframeFilteredToSingleCluster['genres'].values.tolist()
        flattenedGenres = []
        for sublist in genres:
            for item in sublist:
                flattenedGenres.append(item)
        
        #grab top 3 genres in the cluster
        topGenres = []
        genresByFrequency = Counter(flattenedGenres)
        for genre in genresByFrequency.most_common(3):
            topGenres.append(genre[0])
        
        artistNames = dataframeFilteredToSingleCluster['artistNames'].values.tolist()
        flattenedArtistNames = []
        for sublist in artistNames:
            for item in sublist:
                flattenedArtistNames.append(item)

        #grab top 3 artists in the cluster
        topArtists = []
        artistNamesByFrequency = Counter(flattenedArtistNames)
        for artist in artistNamesByFrequency.most_common(3):
            topArtists.append(artist[0])

        #loop thru each audio feature to build up cluster description
        for j in range(len(cluster)):
            audioFeatureValue = cluster[j]            
            clusterObject['audioFeatureCoordinates'][spotifyAudioFeatures[j]] = audioFeatureValue

        clusterObject['mostFrequentArtists'] = topArtists
        clusterObject['mostFrequentGenres'] = topGenres
        clusterObject['trackIDs'] = dataframeFilteredToSingleCluster['trackID'].values.tolist()

        #append the new object to a list, proceed to the next cluster
        clusterObjects.append(clusterObject)
        clusterIndex+=1

    outgoingData = {
        'refreshToken': spotifyRefreshToken,
        'mode': mode,
        'clusters': clusterObjects
    }

    #update clusters userContext field to the new list of cluster objects
    userContextCollection = db['userContext']
    print(userContextCollection.update_one({'userName':userName}, {"$set": {"clusters": clusterObjects}}))

    return json.dumps(outgoingData)

@app.route("/getuserplaylists", methods=["POST"])
def getUserPlaylists():

    spotifyRefreshToken = request.json['refresh_token']
    mode = request.json['mode']
    authorization = auth()
    refreshedSpotifyTokens = authorization.refreshAccessToken(spotifyRefreshToken)
    spotifyAccessToken = refreshedSpotifyTokens['access_token']
    spotifyDataRetrieval = data(spotifyAccessToken)

    thisUserContext = retrieveUserContext(spotifyRefreshToken)

    outgoingData = {
        'userPlaylists':thisUserContext['playlists'],
        'refreshToken': spotifyRefreshToken,
        'mode': mode
        }

    return json.dumps(outgoingData)

@app.route("/setfromcluster", methods=["POST"])
def createSetFromCluster():

    #tokyo at night color scheme #TODO move this to front end
    colors = ['rgba(94, 177, 208, 1)','rgba(112, 87, 146, 1)','rgba(127, 185, 84, 1)','rgba(199, 115, 73, 1)','rgba(214, 90, 119, 1)','rgba(27, 124, 146, 1)','rgba(177, 180, 198, 1)']

    #will create a custom set from the clusters selected stored in usercontext
    spotifyRefreshToken = request.json['refresh_token']
    mode = request.json['mode']
    authorization = auth()
    refreshedSpotifyTokens = authorization.refreshAccessToken(spotifyRefreshToken)
    spotifyAccessToken = refreshedSpotifyTokens['access_token']
    spotifyDataRetrieval = data(spotifyAccessToken)
    profile = spotifyDataRetrieval.profile()
    userName = profile.get("userName")

    thisUserContext = retrieveUserContext(spotifyRefreshToken)

    #list of indexes from request, map this to userContext, create list of track IDs to be included
    clusterIndexString = request.json['form_data']
    print(clusterIndexString)
    if ',' in clusterIndexString:
        clusterIDList = clusterIndexString.split(",")
    else:
        clusterIDList = [clusterIndexString]

    trackIDsForInclusion = []
    for index in clusterIDList:
        selectedCluster = thisUserContext['clusters'][index]
        trackIDsForInclusion.extend(selectedCluster['trackIDs'])

    #get spotify data
    tracks = spotifyDataRetrieval.getTracks(trackIDsForInclusion)
    cleanTracks = spotifyDataRetrieval.cleanTrackData(tracks)
    cleanTracksWithFeatures = spotifyDataRetrieval.getAudioFeatures(cleanTracks)

    print('Completed loading tracks in selected clusters')
    
    #send filtered tracklist to spotifyDataRetrieval#store the pool in spotify and store the playlist ID
    spotifyCreate = create(spotifyAccessToken)
    newPlaylistInfo = spotifyCreate.newPlaylist(userName, "+| music in context - tailored track pool |+", 'Filtered pool of recommended tracks based on your style selections | Music in Context')
    newPlaylistID = spotifyDataRetrieval.URItoID(newPlaylistInfo['uri'])

    #grab URIs into list for submission to spotify
    filteredPoolTrackURIs = []
    for track in cleanTracksWithFeatures:
        filteredPoolTrackURIs.append(spotifyDataRetrieval.idToURI('track', track['trackID']))
    
    if len(filteredPoolTrackURIs)>0:
        n = 50 #spotify playlist addition limit
        for i in range(0, len(filteredPoolTrackURIs), n):  
            spotifyCreate.addTracks(newPlaylistID, filteredPoolTrackURIs[i:i + n])

    #update currentSet field
    userContextCollection = db['userContext']
    print(userContextCollection.update_one({'userName':userName}, {"$set": {"filteredTrackPool": newPlaylistID}}))

    #static fallback DJ Set
    DJSET = [{'trackName': 'TheWeekend', 'trackId': '1rkrZxfScVaKmHdwo92Hr7', 'artistNames': ['David Puentez'], 'artistIds': ['4gSsv9FQDyXx0GUkZYha7v'], 'audioFeatures': {'danceability': 0.805, 'energy': 0.665, 'key': 6, 'loudness': -4.161, 'mode': 1, 'speechiness': 0.0433, 'acousticness': 0.663, 'instrumentalness': 1.3e-06, 'liveness': 0.135, 'valence': 0.77, 'tempo': 125.935, 'type': 'audio_features', 'id': '1rkrZxfScVaKmHdwo92Hr7', 'uri': 'spotify:track:1rkrZxfScVaKmHdwo92Hr7', 'track_href': 'https://api.spotify.com/v1/tracks/1rkrZxfScVaKmHdwo92Hr7', 'analysis_url': 'https://api.spotify.com/v1/audio-analysis/1rkrZxfScVaKmHdwo92Hr7', 'duration_ms': 139048, 'time_signature': 4}, 'genres': ['progressive electro house']}, {'trackName': 'StringsOfLife-AtfcRemix', 'trackId': '0RQ2U4kyyRpa4GhaK5WZPg', 'artistNames': ['Kanu', 'Jude & Frank', 'ATFC'], 'artistIds': ['7qGg5f7GRoEEDsjhetcseQ', '7rUJV3QhhZJVRucw5BK09x', '04L4Y7Hkc1fULKhFbTnSSs'], 'audioFeatures': {'danceability': 0.636, 'energy': 0.864, 'key': 1, 'loudness': -6.365, 'mode': 1, 'speechiness': 0.0455, 'acousticness': 0.011, 'instrumentalness': 0.454, 'liveness': 0.0484, 'valence': 0.755, 'tempo': 124.984, 'type': 'audio_features', 'id': '0RQ2U4kyyRpa4GhaK5WZPg', 'uri': 'spotify:track:0RQ2U4kyyRpa4GhaK5WZPg', 'track_href': 'https://api.spotify.com/v1/tracks/0RQ2U4kyyRpa4GhaK5WZPg', 'analysis_url': 'https://api.spotify.com/v1/audio-analysis/0RQ2U4kyyRpa4GhaK5WZPg', 'duration_ms': 163322, 'time_signature': 4}, 'genres': ['funky tech house', 'italian tech house', 'chicago house', 'deep house', 'disco house', 'funky tech house', 'house', 'tech house', 'tribal house', 'vocal house']}, {'trackName': 'Dvncefloor', 'trackId': '6lBZpeJ5knvYhsMQArHtOX', 'artistNames': ['Cheyenne Giles', 'Knock2'], 'artistIds': ['2FoyDZAnGzikijRdXrocmj', '6mmSS7itNWKbapgG2eZbIg'], 'audioFeatures': {'danceability': 0.829, 'energy': 0.93, 'key': 10, 'loudness': -3.998, 'mode': 0, 'speechiness': 0.156, 'acousticness': 0.000389, 'instrumentalness': 0.0136, 'liveness': 0.054, 'valence': 0.48, 'tempo': 126.025, 'type': 'audio_features', 'id': '6lBZpeJ5knvYhsMQArHtOX', 'uri': 'spotify:track:6lBZpeJ5knvYhsMQArHtOX', 'track_href': 'https://api.spotify.com/v1/tracks/6lBZpeJ5knvYhsMQArHtOX', 'analysis_url': 'https://api.spotify.com/v1/audio-analysis/6lBZpeJ5knvYhsMQArHtOX', 'duration_ms': 152797, 'time_signature': 4}, 'genres': []}, {'trackName': 'HitTheFlow', 'trackId': '7r2VuLH3NqOu0bXF976eFY', 'artistNames': ['Landis'], 'artistIds': ['7bSDGumYzI7Cehekr534Xn'], 'audioFeatures': {'danceability': 0.817, 'energy': 0.987, 'key': 6, 'loudness': -3.344, 'mode': 0, 'speechiness': 0.231, 'acousticness': 0.0038, 'instrumentalness': 0.0432, 'liveness': 0.33, 'valence': 0.643, 'tempo': 128.002, 'type': 'audio_features', 'id': '7r2VuLH3NqOu0bXF976eFY', 'uri': 'spotify:track:7r2VuLH3NqOu0bXF976eFY', 'track_href': 'https://api.spotify.com/v1/tracks/7r2VuLH3NqOu0bXF976eFY', 'analysis_url': 'https://api.spotify.com/v1/audio-analysis/7r2VuLH3NqOu0bXF976eFY', 'duration_ms': 151875, 'time_signature': 4}, 'genres': ['pop edm']}]

    #connect to db, pull in a model DJ set
    djSetDataColection = db['djSetData']
    djSetCursor = djSetDataColection.find({})

    index = 0
    for djSet in djSetCursor:
        print(djSet['URL'])
        DJSET = djSet['tracks_with_features']
        index+=1
        if index > 9:
            break

    #initialize mapreduce lists - aligned with target tracks
    minimumDistances = [999999] * len(DJSET)
    minimumDistanceTracks = ["None"] * len(DJSET)
    minimumDistanceTrackIDs = ["None"] * len(DJSET)
    
    newSetTargets = []

    skipFeatures = []#['liveness']

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

    #loop thru filtered pool and calculate distances
    for cleanTrack in cleanTracksWithFeatures:
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
                        cleanTrack['isUsed'] = True
                        minimumDistanceTracks[arrayIndex] = cleanTrack
                        minimumDistanceTrackIDs[arrayIndex] = cleanTrack['trackID']
                #check against next target
                arrayIndex += 1

        
    #update currentSet field
    userContextCollection = db['userContext']
    print(userContextCollection.update_one({'userName':userName}, {"$set": {"currentSet": minimumDistanceTracks}}))

    trackIDs = []
    for i in range(len(minimumDistanceTracks)):
        minimumDistanceTracks[i]['audioFeatures']['shouldChange'] = 0
        trackIDs.append(minimumDistanceTracks[i]['trackID'])

    #declare framework for outgoing data
    outgoingData = {
        'spotifyAudioFeatures': spotifyAudioFeatures,
        'rawDataByTrack': minimumDistanceTracks,
        'colors': colors,
        'mode': mode,
        'trackIDs': trackIDs
        }

    return json.dumps(outgoingData)


@app.route("/data", methods=["POST"])
def response():
    
    #read in form data from request body
    formData = request.json['form_data']
    spotifyRefreshToken = request.json['refresh_token']
    mode = request.json['mode']
    selectedCLusters = request.json['selectedClusters']

    authorization = auth()
    refreshedSpotifyTokens = authorization.refreshAccessToken(spotifyRefreshToken)
    spotifyAccessToken = refreshedSpotifyTokens['access_token']
    spotifyDataRetrieval = data(spotifyAccessToken)
    profile = spotifyDataRetrieval.profile()
    userName = profile.get("userName")

    thisUserContext = retrieveUserContext(spotifyRefreshToken)

    #tokyo at night color scheme
    colors = ['rgba(94, 177, 208, 1)','rgba(112, 87, 146, 1)','rgba(127, 185, 84, 1)','rgba(199, 115, 73, 1)','rgba(214, 90, 119, 1)','rgba(27, 124, 146, 1)','rgba(177, 180, 198, 1)']

    #select mode here CLUSTER or PLAYLIST
    if mode == 'cluster':
        #DO STUFF
        print("entering CLUSTER mode")
        playlistIDs = formData.split(",")
        #retrieve songs and audio features for user selected playlists
        masterTrackList=[]
        for playlistID in playlistIDs:
            tracks = spotifyDataRetrieval.getPlaylistTracks(spotifyDataRetrieval.idToURI("playlist", playlistID))
            masterTrackList.extend(tracks)

        cleanedMasterTrackList = spotifyDataRetrieval.cleanTrackData(masterTrackList)
        masterTrackListWithFeatures = spotifyDataRetrieval.getAudioFeatures(cleanedMasterTrackList)

         #set up kmeans, check how many songs
        if len(masterTrackListWithFeatures)<5:
            clusters = len(masterTrackListWithFeatures)
        else:
            clusters = 5

        statistics = stats(masterTrackListWithFeatures)
        statistics.kMeans(spotifyAudioFeatures, clusters)
        dataframeWithClusters = statistics.df
        clusterCenterCoordinates = statistics.centers

        #print(dataframeWithClusters.to_dict('records')) This brings us back to list of python dicts

        #create playlists for each kmeans assignment
        spotifyCreate = create(spotifyAccessToken)
        repeatgenres = {}
        minimumDistanceTracks = []
        for i in range(clusters):
            dataBySubGenre = {'audioFeatures':{}}
            selectedClusterCenter = clusterCenterCoordinates[i]
            description = ""
            for j in range(len(spotifyAudioFeatures)):
                dataBySubGenre['audioFeatures'][spotifyAudioFeatures[j]] = round(selectedClusterCenter[j],3)

                audioFeatureName = spotifyAudioFeatures[j]
                audioFeatureValue = selectedClusterCenter[j]

                #convert cluster details to low, medium, high descriptor
                if audioFeatureValue < 0.33:
                    descriptor = 'low'
                elif audioFeatureValue < 0.66:
                    descriptor = 'moderate'
                else:
                    descriptor = 'high'

                entry = str(" "+descriptor+" "+str(spotifyAudioFeatures[j])+"; ")
                description += entry
                #we can return less detail here, maybe 'highly danceable' is sufficient

            description +=" created on {}".format(NICEDATE)
            description+=" by JTokarowski "

            dataframeFilteredToSingleCluster = dataframeWithClusters.loc[dataframeWithClusters['kMeansAssignment'] == i]


            #TODO IMPROVE THIS
            ####################################################################
            genres = dataframeFilteredToSingleCluster['genres'].values.tolist()
            genreslist = genres[0]

            genreDict = {}
            for genre in genreslist:
                g =  genre.replace(" ", "_")
                if g in genreDict:
                    genreDict[g]+=1
                else:
                    genreDict[g]=1

            v=list(genreDict.values())
            k=list(genreDict.keys())

            try:
                maxGenre = k[v.index(max(v))]
            except:
                maxGenre = "¯\_(ツ)_/¯"

            if maxGenre in repeatgenres.keys():
                repeatgenres[maxGenre]+=1
                maxGenre += "_"+str(repeatgenres[maxGenre])
            else:
                repeatgenres[maxGenre]=1

            maxGenre = maxGenre.replace("_", " ")

            #TODO fix this, temp hack to get it working. receiver needs to accept genreName
            dataBySubGenre['trackName'] = maxGenre
            minimumDistanceTracks.append(dataBySubGenre)
    
            newPlaylistInfo = spotifyCreate.newPlaylist(userName, "+| "+str(maxGenre)+" |+", description)
            newPlaylistID = spotifyDataRetrieval.URItoID(newPlaylistInfo['uri'])

            dataframeFilteredToSingleCluster = dataframeFilteredToSingleCluster['trackID']
            newPlaylistTracksIDList = dataframeFilteredToSingleCluster.values.tolist()

            outputPlaylistTracks=[]
            for spotifyID in newPlaylistTracksIDList:
                outputPlaylistTracks.append(spotifyDataRetrieval.idToURI("track",spotifyID))
            
            if len(outputPlaylistTracks)>0:
                n = 50 #spotify playlist addition limit
                for k in range(0, len(outputPlaylistTracks), n):  
                    playlistTracksSegment = outputPlaylistTracks[k:k + n]
                    spotifyCreate.addTracks(newPlaylistID, playlistTracksSegment)


    elif mode == 'playlist':
        #DO STUFF
        print("entering PLAYLIST mode")
        playlistID = formData
        #retrieve songs and audio features for user selected playlist
        tracks = spotifyDataRetrieval.getPlaylistTracks(spotifyDataRetrieval.idToURI("playlist", playlistID))

        cleanedMasterTrackList = spotifyDataRetrieval.cleanTrackData(tracks)
        minimumDistanceTracks = spotifyDataRetrieval.getAudioFeatures(cleanedMasterTrackList)

    else:
        #mode = tunnel
        #TODO checkbox form list the sets we can model the tunnel off of

        trackColors = []

        ################################################################
        ###               TUNNEL  BETA                               ###
        ################################################################

        #static fallback DJ Set
        DJSET = [{'trackName': 'TheWeekend', 'trackId': '1rkrZxfScVaKmHdwo92Hr7', 'artistNames': ['David Puentez'], 'artistIds': ['4gSsv9FQDyXx0GUkZYha7v'], 'audioFeatures': {'danceability': 0.805, 'energy': 0.665, 'key': 6, 'loudness': -4.161, 'mode': 1, 'speechiness': 0.0433, 'acousticness': 0.663, 'instrumentalness': 1.3e-06, 'liveness': 0.135, 'valence': 0.77, 'tempo': 125.935, 'type': 'audio_features', 'id': '1rkrZxfScVaKmHdwo92Hr7', 'uri': 'spotify:track:1rkrZxfScVaKmHdwo92Hr7', 'track_href': 'https://api.spotify.com/v1/tracks/1rkrZxfScVaKmHdwo92Hr7', 'analysis_url': 'https://api.spotify.com/v1/audio-analysis/1rkrZxfScVaKmHdwo92Hr7', 'duration_ms': 139048, 'time_signature': 4}, 'genres': ['progressive electro house']}, {'trackName': 'StringsOfLife-AtfcRemix', 'trackId': '0RQ2U4kyyRpa4GhaK5WZPg', 'artistNames': ['Kanu', 'Jude & Frank', 'ATFC'], 'artistIds': ['7qGg5f7GRoEEDsjhetcseQ', '7rUJV3QhhZJVRucw5BK09x', '04L4Y7Hkc1fULKhFbTnSSs'], 'audioFeatures': {'danceability': 0.636, 'energy': 0.864, 'key': 1, 'loudness': -6.365, 'mode': 1, 'speechiness': 0.0455, 'acousticness': 0.011, 'instrumentalness': 0.454, 'liveness': 0.0484, 'valence': 0.755, 'tempo': 124.984, 'type': 'audio_features', 'id': '0RQ2U4kyyRpa4GhaK5WZPg', 'uri': 'spotify:track:0RQ2U4kyyRpa4GhaK5WZPg', 'track_href': 'https://api.spotify.com/v1/tracks/0RQ2U4kyyRpa4GhaK5WZPg', 'analysis_url': 'https://api.spotify.com/v1/audio-analysis/0RQ2U4kyyRpa4GhaK5WZPg', 'duration_ms': 163322, 'time_signature': 4}, 'genres': ['funky tech house', 'italian tech house', 'chicago house', 'deep house', 'disco house', 'funky tech house', 'house', 'tech house', 'tribal house', 'vocal house']}, {'trackName': 'Dvncefloor', 'trackId': '6lBZpeJ5knvYhsMQArHtOX', 'artistNames': ['Cheyenne Giles', 'Knock2'], 'artistIds': ['2FoyDZAnGzikijRdXrocmj', '6mmSS7itNWKbapgG2eZbIg'], 'audioFeatures': {'danceability': 0.829, 'energy': 0.93, 'key': 10, 'loudness': -3.998, 'mode': 0, 'speechiness': 0.156, 'acousticness': 0.000389, 'instrumentalness': 0.0136, 'liveness': 0.054, 'valence': 0.48, 'tempo': 126.025, 'type': 'audio_features', 'id': '6lBZpeJ5knvYhsMQArHtOX', 'uri': 'spotify:track:6lBZpeJ5knvYhsMQArHtOX', 'track_href': 'https://api.spotify.com/v1/tracks/6lBZpeJ5knvYhsMQArHtOX', 'analysis_url': 'https://api.spotify.com/v1/audio-analysis/6lBZpeJ5knvYhsMQArHtOX', 'duration_ms': 152797, 'time_signature': 4}, 'genres': []}, {'trackName': 'HitTheFlow', 'trackId': '7r2VuLH3NqOu0bXF976eFY', 'artistNames': ['Landis'], 'artistIds': ['7bSDGumYzI7Cehekr534Xn'], 'audioFeatures': {'danceability': 0.817, 'energy': 0.987, 'key': 6, 'loudness': -3.344, 'mode': 0, 'speechiness': 0.231, 'acousticness': 0.0038, 'instrumentalness': 0.0432, 'liveness': 0.33, 'valence': 0.643, 'tempo': 128.002, 'type': 'audio_features', 'id': '7r2VuLH3NqOu0bXF976eFY', 'uri': 'spotify:track:7r2VuLH3NqOu0bXF976eFY', 'track_href': 'https://api.spotify.com/v1/tracks/7r2VuLH3NqOu0bXF976eFY', 'analysis_url': 'https://api.spotify.com/v1/audio-analysis/7r2VuLH3NqOu0bXF976eFY', 'duration_ms': 151875, 'time_signature': 4}, 'genres': ['pop edm']}]

        #connect to db, pull in a model DJ set
        djSetDataColection = db['djSetData']
        djSetCursor = djSetDataColection.find({})
    
        index = 0
        for djSet in djSetCursor:
            print(djSet['URL'])
            DJSET = djSet['tracks_with_features']
            index+=1
            if index > 9:
                break

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

        #grab the pool of recs from spotify
        recommendedTrackPlaylistID = thisUserContext['recommendedTracks']
        recommendedTracks = spotifyDataRetrieval.getPlaylistTracks(spotifyDataRetrieval.idToURI("playlist", recommendedTrackPlaylistID))
        cleanRecommendations = spotifyDataRetrieval.cleanTrackData(recommendedTracks)
        cleanRecommendationsWithFeatures = spotifyDataRetrieval.getAudioFeatures(cleanRecommendations)

        for cleanTrack in cleanRecommendationsWithFeatures:
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
                        cleanTrack['isUsed'] = True
                        minimumDistanceTracks[arrayIndex] = cleanTrack
                        minimumDistanceTrackIDs[arrayIndex] = cleanTrack['trackID']
                #check against next target
                arrayIndex += 1

        
        #update currentSet field
        userContextCollection = db['userContext']
        userContextCollection.update_one({'userName':userName}, {"$set": {"currentSet": minimumDistanceTracks}})


    ################################################################
    ##                    SEND SET TO FRONTEND                    ##
    ################################################################

    #shared scross all methods
    #assign shouldchange indicator
    if mode == "tunnel":
        trackIDs = []
        for i in range(len(minimumDistanceTracks)):
            minimumDistanceTracks[i]['audioFeatures']['shouldChange'] = 0
            trackIDs.append(minimumDistanceTracks[i]['trackID'])
    else:
        trackIDs = ['N/A']

    #declare framework for outgoing data
    outgoingData = {
        'spotifyAudioFeatures': spotifyAudioFeatures,
        'rawDataByTrack': minimumDistanceTracks,
        'colors': colors,
        'mode': mode,
        'trackIDs': trackIDs
        }

    return json.dumps(outgoingData)

#instantiate app
if __name__ == "__main__":
    if ENV == 'heroku':
        app.run(debug=False)
    else:
        app.run(debug=True, port=PORT)