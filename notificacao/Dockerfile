FROM maven:3.9.6-eclipse-temurin-21 AS build

WORKDIR /app
COPY . .

RUN chmod +x mvnw
RUN ./mvnw clean package -DskipTests

FROM openjdk:21-jdk-slim
WORKDIR /app

COPY --from=build /app/target/notificacao-0.0.1-SNAPSHOT.jar .

EXPOSE 8083
CMD ["java", "-jar", "notificacao-0.0.1-SNAPSHOT.jar"]
