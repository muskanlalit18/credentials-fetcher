while :
do
  systemctl stop credentials-fetcher.service
  sleep 2
  systemctl start credentials-fetcher.service
  echo "Restarted credentials fetcher after 30 seconds..."
  sleep 30
done