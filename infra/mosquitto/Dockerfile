FROM eclipse-mosquitto:2.0.20
COPY mosquitto.conf /mosquitto/config/mosquitto.conf
COPY acl /mosquitto/config/acl
COPY --chmod=755 entrypoint.sh /entrypoint-vs.sh
ENTRYPOINT ["/entrypoint-vs.sh"]
CMD ["/usr/sbin/mosquitto", "-c", "/mosquitto/config/mosquitto.conf"]
