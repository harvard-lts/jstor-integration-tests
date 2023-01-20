# jstor-integration-tests

### To start component:
- clone repository
- cp .env.example to .env
- cp celeryconfig.py.example to celeryconfig.py and put in credentials
- make sure logs/jstor_itests directory exists (need to fix)
- bring up docker
- - docker-compose -f docker-compose-local.yml up --build -d --force-recreate --remove-orphans
- start test by going to the browser at this url:
- - https://localhost:24005/integration
- stop docker 
- - docker-compose -f docker-compose-local.yml down
