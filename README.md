# README

## 系统架构

前端：Flask

后端：SQL Sever

## 环境配置

**python环境准备**

```pyhton
pip install flask pymssql
```



**数据库准备**

在本地电脑上建一个数据库，名字为FleetDB，配置sa用户密码为123456

```
DB_CONFIG = {

    "server": "localhost",      # 或 IP

    "user": "sa",               # SQL Server 用户

    "password": "123456",    # 密码

    "database": "FleetDB",    # 数据库名

    "charset": "utf8"

}
```



**建表**

在SSMS上执行`init_table.sql`即可



**Flask连接数据库准备**

需要开启TCP等服务，具体参考网上资料

## 运行

在databaseFinal文件夹下运行命令

```
flask run
```

## 项目结构

databaseFinal

│  app.py    # Flask 入口
│  db.py    # 数据库连接模块
│
├─document # 一些文档
│      
│
└─sql    # sql代码
        

## 改动

考虑到对中文的支持，实际建表把类型varchar改为nvarchar，比较简单

驾照等级C3改为C2
