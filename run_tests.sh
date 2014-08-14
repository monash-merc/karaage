#!/bin/bash
DIR=$(cd -P -- "$(dirname -- "$0")" && pwd -P)

RETURN=0
cd $DIR

if [ -n "$*" ]; then
    TESTS="$@"
else
    TESTS="kgapplications.tests"
fi

echo ""
echo "FLAKE8"
echo "############################"
flake8 --ignore=E501 --filename="migrations" .
flake8 --exclude="migrations" .
if [ ! $? -eq 0 ]
then
    RETURN=1
fi
echo -e "\n\n"

echo ""
echo "STATIC FILES"
echo "############################"
./manage.py collectstatic --settings=kgapplications.tests.settings -v 2 --noinput

echo ""
echo "TESTS - Python 2"
echo "############################"
python2 ./manage.py test --settings=kgapplications.tests.settings -v 2 $TESTS
if [ ! $? -eq 0 ]
then
    RETURN=1
fi

echo ""
echo "TESTS - Python 3"
echo "############################"
python3 ./manage.py test --settings=kgapplications.tests.settings -v 2 $TESTS
if [ ! $? -eq 0 ]
then
    RETURN=1
fi

exit $RETURN
