## First deploy (after docker engine installed)
sudo install -d -o "$(id -un)" -g "$(id -gn)" /srv/dst-helper

git clone YOUR_GITHUB_REPOSITORY_URL /srv/dst-helper
cd /srv/dst-helper

(may need to) sudo usermod -aG docker YOUR_CURRENT_USER
(restart the session)

docker compose up -d --build

## Update
cd /srv/dst-helper
git pull --ff-only
docker compose up -d --build