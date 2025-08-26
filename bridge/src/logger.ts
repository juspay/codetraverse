import * as fs from 'fs';
import * as path from 'path';
import os from "os";

export interface LoggerConfig {
  logFilePath?: string;
  enableTimestamp?: boolean;
  enableConsole?: boolean;
}

export class FileLogger {
  private logFilePath: string;
  private enableTimestamp: boolean;
  private enableConsole: boolean;

  constructor(config: LoggerConfig = {}) {
    this.logFilePath = path.join(`${os.homedir()}/.xyne/`, 'codetraverse.log');
    this.enableTimestamp = config.enableTimestamp ?? true;
    this.enableConsole = config.enableConsole ?? false;
    
    // Ensure log directory exists and test write access
    try {
      const logDir = path.dirname(this.logFilePath);
      if (!fs.existsSync(logDir)) {
        fs.mkdirSync(logDir, { recursive: true });
      }
      
      // Test write access by creating the file if it doesn't exist
      if (!fs.existsSync(this.logFilePath)) {
        fs.writeFileSync(this.logFilePath, '');
      }
    } catch (error) {
      // If we can't write to the specified location, fallback to temp directory
      this.logFilePath = path.join(os.tmpdir(), 'codetraverse.log');
      if (this.enableConsole) {
        process.stderr.write(`Failed to create log file at original location, using fallback: ${this.logFilePath}\n`);
      }
    }
  }

  private formatMessage(level: string, message: string): string {
    const timestamp = this.enableTimestamp ? new Date().toISOString() : '';
    const prefix = this.enableTimestamp ? `[${timestamp}] [${level.toUpperCase()}] ` : `[${level.toUpperCase()}] `;
    return prefix + message + '\n';
  }

  private writeToFile(formattedMessage: string): void {
    try {
      fs.appendFileSync(this.logFilePath, formattedMessage);
    } catch (error) {
      // Fallback to console if file write fails
      if (this.enableConsole) {
        process.stderr.write(`Failed to write to log file: ${error}\n`);
        process.stderr.write(`Original message: ${formattedMessage}`);
      }
    }
  }

  log(message: string): void {
    const formatted = this.formatMessage('info', message);
    this.writeToFile(formatted);
    if (this.enableConsole) {
      process.stdout.write(formatted);
    }
  }

  info(message: string): void {
    this.log(message);
  }

  warn(message: string): void {
    const formatted = this.formatMessage('warn', message);
    this.writeToFile(formatted);
    if (this.enableConsole) {
      process.stderr.write(formatted);
    }
  }

  error(message: string): void {
    const formatted = this.formatMessage('error', message);
    this.writeToFile(formatted);
    if (this.enableConsole) {
      process.stderr.write(formatted);
    }
  }

  debug(message: string): void {
    const formatted = this.formatMessage('debug', message);
    this.writeToFile(formatted);
    if (this.enableConsole) {
      process.stdout.write(formatted);
    }
  }
}

// Create a default logger instance
export const logger = new FileLogger();

// Convenience functions that match console.log API
export const logToFile = {
  log: (message: string) => logger.log(message),
  info: (message: string) => logger.info(message),
  warn: (message: string) => logger.warn(message),
  error: (message: string) => logger.error(message),
  debug: (message: string) => logger.debug(message)
};
