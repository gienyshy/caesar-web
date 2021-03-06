#!/bin/sh

CAESAR_DIR=/var/django/caesar

# Set time zone.
#    **** comment out for now, not sure Caesar needs this
#echo America/New_York > /etc/timezone
#/usr/sbin/dpkg-reconfigure tzdata

# Install Linux packages we need.
apt-get update
apt-get install -y python-dev python-numpy python-psycopg2 python-pip # for Django
apt-get install -y apache2 apache2-dev libapache2-mod-wsgi # for Apache
apt-get install -y libmysqlclient-dev libldap2-dev libsasl2-dev # MySQL, LDAP
apt-get install -y oracle-java8-installer # in order to run checkstyle

# Install Python packages we need.
cd /tmp
pip install -r $CAESAR_DIR/requirements.txt

# Set up SSL
a2enmod ssl

# Install Caesar into Apache
ln -sf $CAESAR_DIR/apache/caesar.conf /etc/apache2/sites-available
a2ensite caesar

# Start or restart Apache
apachectl graceful
