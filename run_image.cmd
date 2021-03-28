docker ps -aq --filter name=mixcloud_fake_plays > res_img_id
set /p Res_Img_Id=<res_img_id
del res_img_id
docker rm -f %Res_Img_Id%
docker run --name mixcloud_fake_plays -d mixcloud_fake_plays