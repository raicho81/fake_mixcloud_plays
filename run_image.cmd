docker ps -aq --filter name=mixcloud_fake_plays > res_img_ids
for /f "Tokens=* Delims=" %%x in (res_img_ids) do docker rm -f %%x
del res_img_ids
docker run --name mixcloud_fake_plays -d mixcloud_fake_plays