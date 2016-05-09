package io.vertx.lang.python;

import io.vertx.core.AbstractVerticle;
import io.vertx.core.Future;
import io.vertx.core.Verticle;
import io.vertx.core.Vertx;
import io.vertx.core.VertxException;
import io.vertx.core.spi.VerticleFactory;

import java.lang.ProcessBuilder.Redirect;
import java.net.InetAddress;

import py4j.GatewayServer;

/**
 * @author <a href="http://tfox.org">Tim Fox</a>
 */
public class PythonVerticleFactory implements VerticleFactory {

  private Vertx vertx;
  private GatewayServer gateway;
  private int port = 25333;
  private int client_port = 24333;

  @Override
  public void init(Vertx vertx) {
    this.vertx = vertx;
  }

  public Vertx getVertx() {
    return vertx;
  }

  @Override
  public String prefix() {
    return "py";
  }

  @Override
  public Verticle createVerticle(String verticleName, ClassLoader classLoader) throws Exception {
    init();
    verticleName = VerticleFactory.removePrefix(verticleName);
    return new PythonVerticle(verticleName);
  }

  public class ProcessMonitor implements Runnable {
    private Process proc;
    private PythonVerticle vert;

    public ProcessMonitor(Process p, PythonVerticle v) {
      proc = p;
      vert = v;
    }

    public void run() {
      try {
        proc.waitFor();
        vert.stop();
      }
      catch (Exception ex) { System.out.println(ex);}
    }

  }

  public class PythonVerticle extends AbstractVerticle {

    private final String verticleName;

    private PythonVerticle(String verticleName) {
      this.verticleName = verticleName;
    }

    private Process process;
    private boolean asyncStart;
    private Future<Void> startFuture;
    private Future<Void> stopFuture;

    @Override
    public void start(Future<Void> startFuture) throws Exception {
      ProcessBuilder pb = new ProcessBuilder("python", "-u", verticleName, String.valueOf(port), String.valueOf(client_port));
      pb.redirectOutput(Redirect.INHERIT);
      pb.redirectError(Redirect.INHERIT);
      process = pb.start();
      new Thread(new ProcessMonitor(process, this)).start();
      if (asyncStart) {
        this.startFuture = startFuture;
      } else {
        startFuture.complete();
      }
    }

    @Override
    public void stop(Future<Void> stopFuture) throws Exception {
      if (process != null && process.isAlive()) {
        process.destroy();
      }
      stopFuture.complete();
    }

    public void started(boolean started) {
      if (startFuture != null) {
        if (started) {
          startFuture.complete();
        }
      } else if (!started) {
        asyncStart = true;
      }
    }

    public void stopped(boolean stopped) {
      if (stopFuture != null) {
        if (stopped) {
          stopFuture.complete();
        }
      }
    }
  }

  @Override
  public void close() {
    if (gateway != null) {
      gateway.shutdown();
    }
  }

  private synchronized void init() {
    if (gateway == null) {
      boolean connected = false;
      while (!connected) {
        try {
          gateway = new GatewayServer(this, port, client_port,
                                      InetAddress.getByName(GatewayServer.DEFAULT_ADDRESS),
                                      InetAddress.getByName(GatewayServer.DEFAULT_ADDRESS),
                                      GatewayServer.DEFAULT_CONNECT_TIMEOUT,
                                      GatewayServer.DEFAULT_READ_TIMEOUT,
                                      null
                                      );
          gateway.start();
          connected = true;
        } catch (Exception e) {
          // If port seemed to be taken, increment port/client_port together.
          // This is kind of hacky, since we really have no confirmation that
          // client_port is unused, even if port works.
          port++;
          client_port++;
        }
        if (port > 25340) {
          throw new VertxException("Failed to bind to port");
        }
      }
    }
  }

}
