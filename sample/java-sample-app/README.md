# SQL Server Kerberos Authentication Java Application

A simple Java application that connects to Microsoft SQL Server using Kerberos authentication and executes a simple Select command on the database.

## Prerequisites

- Java 11 or higher
- Microsoft JDBC Driver for SQL Server (JDBC driver used to create this app is ```mssql-jdbc-12.8.1.jre8.jar```)
- Valid Kerberos ticket (can be verified using `klist`)
- SQL Server configured for Kerberos authentication

## Files Required

1. `SQLServerKerberosConnection.class` - The compiled Java class file
2. `mssql-jdbc-12.8.1.jre8.jar` - Microsoft JDBC driver for SQL Server

## Environment Setup

1. Ensure you have a valid Kerberos ticket:
```
klist
```

2. set the ```KRB5CCNAME``` in the environment to the krb5cc directory of a ticket. For example:
```
export KRB5CCNAME=/var/credentials-fetcher/krbdir/<lease_id>/WebApp01/krb5cc
```
Verify that the variable has been set correctly using ```echo $KRB5CCNAME```

3. Compile and run the Java file like so
```
javac --release 11 -cp .:mssql-jdbc-12.8.1.jre8.jar SQLServerKerberosConnection.java
java -cp .:mssql-jdbc-12.8.1.jre8.jar SQLServerKerberosConnection
```

4. You should see the following output
```
Connected successfully using Kerberos authentication.
+---------------------------+---------------------------+---------------------------+---------------------------+---------------------------+
| EmpID                     | EmpName                   | Designation               | Department                | JoiningDate               |
+---------------------------+---------------------------+---------------------------+---------------------------+---------------------------+
| 1                         | CHIN YEN                  | LAB ASSISTANT             | LAB                       | 2022-03-05 03:57:09.967   |
+---------------------------+---------------------------+---------------------------+---------------------------+---------------------------+
| 2                         | MIKE PEARL                | SENIOR ACCOUNTANT         | ACCOUNTS                  | 2022-03-05 03:57:09.967   |
+---------------------------+---------------------------+---------------------------+---------------------------+---------------------------+
| 3                         | GREEN FIELD               | ACCOUNTANT                | ACCOUNTS                  | 2022-03-05 03:57:09.967   |
+---------------------------+---------------------------+---------------------------+---------------------------+---------------------------+
| 4                         | DEWANE PAUL               | PROGRAMMER                | IT                        | 2022-03-05 03:57:09.967   |
+---------------------------+---------------------------+---------------------------+---------------------------+---------------------------+
| 5                         | MATTS                     | SR. PROGRAMMER            | IT                        | 2022-03-05 03:57:09.967   |
+---------------------------+---------------------------+---------------------------+---------------------------+---------------------------+
| 6                         | PLANK OTO                 | ACCOUNTANT                | ACCOUNTS                  | 2022-03-05 03:57:09.967   |
```