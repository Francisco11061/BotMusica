FROM eclipse-temurin:17-jre-alpine
WORKDIR /app
COPY Lavalink.jar .
COPY application.yml .
RUN mkdir -p plugins
COPY plugins/ plugins/
EXPOSE 2333
CMD ["java", "-jar", "Lavalink.jar"]