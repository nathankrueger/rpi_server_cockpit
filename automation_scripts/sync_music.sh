REMOTE_PI_HOST=manserv
REMOTE_PI_USER=dennis
REMOTE_FOLDER=/media/dennis/Passport4TB/Music/
LOCAL_FOLDER=/home/nkrueger/Music/

cd $LOCAL_FOLDER; rsync -rRPv . $REMOTE_PI_USER@$REMOTE_PI_HOST:$REMOTE_FOLDER