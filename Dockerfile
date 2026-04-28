FROM eclipse-temurin:17-jre-alpine
WORKDIR /app
RUN wget https://github.com/lavalink-devs/Lavalink/releases/download/4.0.8/Lavalink.jar
COPY application.yml .
RUN mkdir -p plugins
COPY plugins/ plugins/
EXPOSE 2333
CMD ["java", "-jar", "Lavalink.jar"]