docker rm -f $(docker ps -aq --filter name=mixcloud_fake_plays)
docker run --name mixcloud_fake_plays -d mixcloud_fake_plays