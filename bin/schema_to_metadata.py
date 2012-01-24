#!/usr/bin/env python

# 
# LSST Data Management System
# Copyright 2008, 2009, 2010 LSST Corporation.
# 
# This product includes software developed by the
# LSST Project (http://www.lsst.org/).
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# 
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the LSST License Statement and 
# the GNU General Public License along with this program.  If not, 
# see <http://www.lsstcorp.org/LegalNotices/>.
#

# want to extract:
# per table:
#   name
#   engine
# per column:
#   type 
#   notnull
#   defaultValue
#   <descr>...</descr>
#   <unit>...</unit>
#   <ucd>...</ucd>


import commands
import optparse
import os
import re
import sys

###############################################################################
# Configuration information
###############################################################################

# Fields for tables in the metadata (values obtained with custom code).
tableFields = ["engine",  "description"]

columnFields = ["description", "type", "notNull", "defaultValue",
                "unit", "ucd", "displayOrder"]

# Fields for md_Index table
indexFields = ["type", "columns"]

numericFields = ["notNull", "displayOrder"]

###############################################################################
# Usage and command line processing
###############################################################################

usage = """%prog -i inputSchemaFile.sql -v VERSION

The script extract information from the input file and generates the output
file that can be used by the schema browser. The output will be placed in
/tmp/metadata_{VERSION}.sql

The input schema file should be in subversion (svn info -R will be executed
on that file)

"""

parser = optparse.OptionParser(usage=usage)
parser.add_option("-i", help="Input schema file")
parser.add_option("-v", help="Version, e.g., DC3b, PT1_1")

options, arguments = parser.parse_args()

if not options.i or not options.v:
    sys.stderr.write(os.path.basename(sys.argv[0]) + usage[5:])
    sys.exit(1)

if not os.path.isfile(options.i):
    sys.stderr.write("File '%s' does not exist\n" % iF)
    sys.exit(1)

###############################################################################
# DDL for creating database and tables
###############################################################################

databaseDDL = """
DROP DATABASE IF EXISTS lsst_schema_browser_%s;
CREATE DATABASE lsst_schema_browser_%s;
USE lsst_schema_browser_%s;

""" % (options.v, options.v, options.v)

# Names of fields in these tables after "name" must match the names in the
# Fields variables above.

tableDDL = """
CREATE TABLE md_Table (
	tableId INTEGER NOT NULL PRIMARY KEY,
	name VARCHAR(255) NOT NULL UNIQUE,
	engine VARCHAR(255),
	description TEXT
);

CREATE TABLE md_Column (
	columnId INTEGER NOT NULL PRIMARY KEY,
	tableId INTEGER NOT NULL REFERENCES md_Table (tableId),
	name VARCHAR(255) NOT NULL,
	description TEXT,
	type VARCHAR(255),
	notNull INTEGER DEFAULT 0,
	defaultValue VARCHAR(255),
	unit VARCHAR(255),
	ucd VARCHAR(255),
        displayOrder INTEGER NOT NULL,
	INDEX md_Column_idx (tableId, name)
);

CREATE TABLE md_Index (
	indexId INTEGER NOT NULL PRIMARY KEY,
	tableId INTEGER NOT NULL REFERENCES md_Table (tableId),
	type VARCHAR(64) NOT NULL,
	columns VARCHAR(255) NOT NULL,
	INDEX md_Column_idx (tableId)
) ;

CREATE TABLE md_DbDescr (
	schemaFile VARCHAR(255),
	revision VARCHAR(64)
);

"""

###############################################################################
# Standard header to be prepended
###############################################################################

LSSTheader = """
-- LSST Database Metadata
-- $Revision$
-- $Date$
--
-- See <http://dev.lsstcorp.org/trac/wiki/Copyrights>
-- for copyright information.


--  ! ! !    W A R N I N G    ! ! !
-- do NOT update this file by hand. It is auto-generated by the
-- script cat/bin/schema_to_metadata.sql based on the schema 
-- description tables from schema file located in cat/sql/
"""


################################################################################
# 
################################################################################

oFName = "/tmp/metadata_%s.sql" % options.v
oF = open(oFName, mode='wt')
oF.write(LSSTheader)
oF.write(databaseDDL)
oF.write(tableDDL)

###############################################################################
# Parse sql
###############################################################################

def isIndexDefinition(c):
    return c in ["PRIMARY", "KEY", "INDEX", "UNIQUE"]

def isCommentLine(str):
    return re.match('[\s]*--', str) is not None

def isUnitLine(str):
    return re.search(r'<unit>(.+)</unit>', str) is not None

def retrieveUnit(str):
    xx = re.compile(r'<unit>(.+)</unit>')
    x = xx.search(str)
    return x.group(1)

def containsDescrTagStart(str):
    return re.search(r'<descr>', str) is not None

def containsDescrTagEnd(str):
    return re.search(r'</descr>', str) is not None

def retrieveDescr(str):
    xx = re.compile(r'<descr>(.+)</descr>')
    x = xx.search(str)
    return x.group(1)
    
def retrieveDescrStart(str):
    xx = re.compile('<descr>(.+)')
    x = xx.search(str)
    return x.group(1)

def retrieveDescrMid(str):
    xx = re.compile('[\s]*--(.+)')
    x = xx.search(str)
    return x.group(1)

def retrieveDescrEnd(str):
    if re.search('-- </descr>', str):
        return ''
    xx = re.compile('[\s]*--(.+)</descr>')
    x = xx.search(str)
    return x.group(1)
    
def retrieveIsNotNull(str):
    if re.search('NOT NULL', str):
        return '1'
    return '0'

def retrieveType(str):
    arr = str.split()
    t = arr[1]
    if t == "FLOAT(0)":
        return "FLOAT"
    return t

def retrieveDefaultValue(str):
    if re.search(' DEFAULT ', str) is None:
        return None
    arr = str.split()
    returnNext = 0
    for a in arr:
        if returnNext:
            return a.rstrip(',')
        if a == 'DEFAULT':
            returnNext = 1

#example strings:
#"    PRIMARY KEY (id),",
#"    KEY IDX_sId (sId ASC),",
#"    KEY IDX_d (decl DESC)",
#"    UNIQUE UQ_AmpMap_ampName(ampName)"
#"    UNIQUE UQ_x(xx DESC, yy),"

def retrieveColumns(str):
    xx = re.search('[\s\w_]+\(([\w ,]+)\)', str.rstrip())
    xx = xx.group(1).split() # skip " ASC", " DESC" etc
    s = ''
    for x in xx:
        if not x == 'ASC' and not x == 'DESC':
            s += x
            if x[-1] == ',':
                s += ' '
    return s


in_table = None
in_col = None
in_colDescr = None
table = {}

dbDescr_file = None
dbDescr_rev = None

tableStart = re.compile(r'CREATE TABLE (\w+)*')
tableEnd = re.compile(r"\)")
engineLine = re.compile(r'\) (ENGINE|TYPE)=(\w+)*;')
columnLine = re.compile(r'[\s]+(\w+) ([\w\(\)]+)')
descrStart = re.compile(r'<descr>')
descrEnd = re.compile(r'</descr>')
unitStart = re.compile(r'<unit>')
unitEnd = re.compile(r'</unit>')
zzDbDescrF = re.compile(r'INSERT INTO ZZZ_Db_Description\(f\) VALUES\(\'([\w.]+)')

colNum = 1

tableNumber = 1000 # just for hashing, not really needed by schema browser

iF = open(options.i, mode='r')
for line in iF:
    #print "processing ", line
    m = tableStart.search(line)
    if m is not None:
        tableName = m.group(1)
        table[tableNumber] = {}
        table[tableNumber]["name"] = tableName
        colNum = 1
        in_table = table[tableNumber]
        tableNumber += 1
        in_col = None
        #print "Found table ", in_table
    elif tableEnd.match(line):
        m = engineLine.match(line)
        if m is not None:
            engineName = m.group(2)
            in_table["engine"] = engineName
        #print "end of the table"
        #print in_table
        in_table = None
    elif in_table is not None: # process columns for given table
        m = columnLine.match(line)
        if m is not None:
            firstWord = m.group(1)
            if isIndexDefinition(firstWord):
                t = "-"
                if firstWord == "PRIMARY":
                    t = "PRIMARY KEY"
                elif firstWord == "UNIQUE":
                    t = "UNIQUE"
                idxInfo = {"type" : t,
                           "columns" : retrieveColumns(line)
                           }
                if "indexes" not in in_table:
                    in_table["indexes"] = []
                in_table["indexes"].append(idxInfo)
            else:
                in_col = {"name" : firstWord, 
                          "displayOrder" : str(colNum),
                          "type" : retrieveType(line),
                          "notNull" : retrieveIsNotNull(line),
                          }
                dv = retrieveDefaultValue(line)
                if dv is not None:
                    in_col["defaultValue"] = dv
                colNum += 1
                if "columns" not in in_table:
                    in_table["columns"] = []
                in_table["columns"].append(in_col)
            #print "found col: ", in_col
        elif isCommentLine(line): # handle comments
            if in_col is None:    # table comment

                if containsDescrTagStart(line):
                    if containsDescrTagEnd(line):
                        in_table["description"] = retrieveDescr(line)
                    else:
                        in_table["description"] = retrieveDescrStart(line)
                elif "description" in in_table:
                    if containsDescrTagEnd(line):
                        in_table["description"] += retrieveDescrEnd(line)
                    else:
                        in_table["description"] += retrieveDescrMid(line)

            else:
                                  # column comment
                if containsDescrTagStart(line):
                    if containsDescrTagEnd(line):
                        in_col["description"] = retrieveDescr(line)
                    else:
                        in_col["description"] = retrieveDescrStart(line)
                        in_colDescr = 1
                elif in_colDescr:
                    if containsDescrTagEnd(line):
                        in_col["description"] += retrieveDescrEnd(line)
                        in_colDescr = None
                    else:
                        in_col["description"] += retrieveDescrMid(line)

                                  # units
                if isUnitLine(line):
                    in_col["unit"] = retrieveUnit(line)
    elif zzDbDescrF.match(line): # process "INSERT INTO ZZZ_Db_Description"
        m = zzDbDescrF.search(line)
        dbDescr_file = m.group(1)
        dbDescr_rev = commands.getoutput("git describe --dirty")

iF.close()
#print table

###############################################################################
# Output DML
###############################################################################

def handleField(ptr, field, indent):
    if field not in ptr:
        return
    q = '"'
    if field in numericFields:
        q = ''
    oF.write(",\n")
    oF.write("".join(["\t" for i in xrange(indent)]))
    oF.write(field + " = " + q + ptr[field] + q)


if dbDescr_file and dbDescr_rev:
    oF.write("".join(["-- " for i in xrange(25)]) + "\n\n")
    oF.write("INSERT INTO md_DbDescr\n")
    oF.write('SET schemaFile = "%s", revision = "%s"' % \
                 (dbDescr_file, dbDescr_rev))
    oF.write(";\n\n")


tableId = 0
colId = 0
idxId = 0
for k in sorted(table.keys(), key=lambda x: table[x]["name"]):
    t = table[k]
    tableId += 1
    oF.write("".join(["-- " for i in xrange(25)]) + "\n\n")
    oF.write("INSERT INTO md_Table\n")
    oF.write('SET tableId = %d, name = "%s"' % (tableId, t["name"]))
    for f in tableFields:
        handleField(t, f, 1)
    oF.write(";\n\n")

    if "columns" in t:
        for c in t["columns"]:
            colId += 1
            oF.write("\tINSERT INTO md_Column\n")
            oF.write('\tSET columnId = %d, tableId = %d, name = "%s"' %
                    (colId, tableId, c["name"]))
            for f in columnFields:
                handleField(c, f, 2)
            oF.write(";\n\n")

    if "indexes" in t:
        for c in t["indexes"]:
            idxId += 1
            oF.write("\tINSERT INTO md_Index\n")
            oF.write('\tSET indexId = %d, tableId = %d' % (idxId, tableId))
            for f in indexFields:
                handleField(c, f, 2)
            oF.write(";\n\n")

oF.close()
