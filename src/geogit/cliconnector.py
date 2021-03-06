import subprocess
import os
import tempfile
import geogit
from feature import Feature
from tree import Tree
from commit import Commit
import datetime
from diff import Diffentry
from commitish import Commitish
from geogitexception import GeoGitException
from shapely.wkt import loads

def _run(command):         
                                                                                                            
    command = ['geogit'] + command
    print " ".join(command)
    output = []    
    proc = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, 
                            stdin=subprocess.PIPE,stderr=subprocess.STDOUT, universal_newlines=True)
    for line in iter(proc.stdout.readline, ""):        
        line = line.strip("\n")
        output.append(line)        
    returncode = proc.returncode    
    if returncode:
        raise GeoGitException("\n".join(output))       
    return output
    
class CLIConnector():
    ''' A connector that calls the CLI version of geogit and parses CLI output'''
    
    def setRepository(self, repo):
        self.repo = repo        

    @staticmethod
    def clone(url, dest):        
        commands = ['clone', url, dest]
        _run(commands)        
                
    def run(self, command):   
        os.chdir(self.repo.url)
        return _run(command)  

    def revparse(self, rev):
        commands = ['rev-parse', rev]
        output = self.run(commands)
        id = output[0].strip()
        if len(id) != 40:
            raise GeoGitException("Cannot resolve the provided reference")        
        return id
           
    def head(self):
        self.checkisrepo()
        headfile = os.path.join(self.repo.url, '.geogit', 'HEAD')
        f = open(headfile)
        line = f.readline()
        f.close()
        ref = line.strip().split(' ')[-1]
        branchname = ref[len("refs/heads/"):]
        return Commitish(self.repo, branchname)
    
    def isrebasing(self):
        self.checkisrepo()
        headfile = os.path.join(self.repo.url, '.geogit', 'ORIG_HEAD')
        branchfile =  os.path.join(self.repo.url, '.geogit', 'rebase-apply', 'branch')
        return os.path.exists(headfile) and os.path.exists(branchfile) 
    
    def ismerging(self):
        self.checkisrepo()
        headfile = os.path.join(self.repo.url, '.geogit', 'ORIG_HEAD')
        branchfile =  os.path.join(self.repo.url, '.geogit', 'rebase-apply', 'branch')
        return os.path.exists(headfile) and not os.path.exists(branchfile)    
        
    
    def checkisrepo(self):
        if not os.path.exists(os.path.join(self.repo.url, '.geogit')):
            raise GeoGitException("Not a valid GeoGit repository: " + self.repo.url)
        
    
    def children(self, ref = 'HEAD', path = None, recursive = False):
        children = []    
        if path is None:
            fullref = ref
        else:
            fullref = ref + ':' + path 
        commands = ['ls-tree', fullref, "-v"]
        if recursive:
            commands.append("-r")
        output = self.run(commands)    
        for line in output:
            if line != '':                
                tokens = line.split(" ")
                if tokens[1] == "feature":
                    children.append(Feature(self.repo, ref, tokens[3]))
                elif tokens[1] == "tree":
                    children.append(Tree(self.repo, ref, tokens[3]))
        return children   
    
    def commitFromString(self, lines):                
        message = False
        messagetext = None
        parent = None
        commitid = None
        for line in lines:
            tokens = line.split(' ')
            if message:
                if line.startswith("\t") or line.startswith(" "):
                    messagetext = line.strip() if messagetext is None else messagetext + "\n" + line.strip()
                else:
                    message = False            
            else:                
                if tokens[0] == 'commit':
                    commitid = tokens[1]
                if tokens[0] == 'tree':
                    tree = tokens[1]                    
                if tokens[0] == 'parent':
                    if len(tokens) == 2 and tokens[1] != "":
                        parent = tokens[1]                    
                elif tokens[0] == 'author':
                    author = " ".join(tokens[1:-3])
                    authordate = datetime.datetime.fromtimestamp(int(tokens[-2])//1000)                
                elif tokens[0] == 'committer':
                    committer = tokens[1]
                    committerdate = datetime.datetime.fromtimestamp(int(tokens[-2])//1000)
                elif tokens[0] == 'message':
                    message = True                
            
        if commitid is not None:
            c = Commit(self.repo, commitid, tree, parent, messagetext, author, authordate, committer, committerdate)
            return c
        else:
            return None

    def logentryFromString(self, lines):
        diffs = []
        changes = False
        message = False
        messagetext = None
        parent = None
        commitid = None
        for line in lines:
            tokens = line.split(' ')
            if message:
                if line.startswith("\t") or line.startswith(" "):
                    messagetext = line.strip() if messagetext is None else messagetext + "\n" + line.strip()
                else:
                    message = False
            if changes:                                        
                diffs.append(self.diffentryFromString(line))             
            else:                
                if tokens[0] == 'commit':
                    commitid = tokens[1]
                if tokens[0] == 'tree':
                    tree = tokens[1]                    
                if tokens[0] == 'parent':
                    if len(tokens) == 2 and tokens[1] != "":
                        parent = tokens[1]                    
                elif tokens[0] == 'author':
                    author = " ".join(tokens[1:-3])
                    authordate = datetime.datetime.fromtimestamp(int(tokens[-2])//1000)                
                elif tokens[0] == 'committer':
                    committer = tokens[1]
                    committerdate = datetime.datetime.fromtimestamp(int(tokens[-2])//1000)
                elif tokens[0] == 'message':
                    message = True
                elif tokens[0] == 'changes':
                    changes = True                
            
        if commitid is not None:
            c = Commit(self.repo, commitid, tree, parent, messagetext, author, authordate, committer, committerdate)
            return (c, diffs)
        else:
            return None

    def addremote(self, name, url):
        commands = ["remote", "add", name, url]
        self.run(commands)
        
    def removeremote(self, name):
        commands = ["remote", "remove", name]
        self.run(commands)     
        
    def remotes(self):
        commands = ["remote", "list", "-v"]
        output = self.run(commands)
        remotes = []
        names = []
        for line in output:
            tokens = line.split(" ")
            if tokens[0] not in names:
                remotes.append((tokens[0], tokens[1]))
                names.append(tokens[0])
        return remotes        
        
    def log(self, ref, path = None):
        commits = []
        commands = ['rev-list', ref, '--changed']        
        if path is not None:
            commands.extend(["-p", path])
        output = self.run(commands)
        commitlines = []
        for line in output:
            if line == '':
                commit = self.commitFromString(commitlines)
                if commit is not None:
                    commits.append(commit)
                    commitlines = []
            else:
                commitlines.append(line)            
            
        if commitlines:
            commit = self.commitFromString(commitlines)
            if commit is not None:
                commits.append(commit)
        return commits 
    
    def conflicts(self):
        commands = ["conflicts", "--refspecs-only"]
        lines = self.run(commands)
        _conflicts = {}        
        for line in lines:
            if line.startswith("No elements need merging"):
                return {}
            tokens = line.split(" ")
            _conflicts[tokens[0]] = (tokens[1], tokens[2], tokens [3])
        return _conflicts
            
    
    def checkout(self, ref, paths = None):
        commands = ['checkout', ref]
        if paths is not None and len(paths) > 0:            
            commands.append("-p")
            commands.extend(paths)
        self.run(commands)
        
    def reset(self, ref, mode = 'hard'):
        self.run(['reset', ref, "--" + mode])                    
        
    def branches(self):    
        branches = []        
        output = self.run(['show-ref'])    
        for line in output:            
            tokens = line.strip().split(" ")
            if tokens[1].startswith("refs/heads/"):
                branches.append((tokens[1][len("refs/heads/"):], tokens[0]))
        return branches
    
    def tags(self):
        tags = []
        output = self.run(['show-ref'])    
        for line in output:            
            tokens = line.strip().split(" ")
            if tokens[1].startswith("refs/tags/"):
                tags.append((tokens[1][len("refs/tags/"):], tokens[0]))
        return tags 

    
    def createbranch(self, ref, name, force = False, checkout = False):
        commands = ['branch', name, ref]
        if force:
            commands.append('-f')
        if checkout:
            commands.append('-c')            
        self.run(commands)

    def deletebranch(self, name):        
        self.run(['branch', '-d', name])     

    def createtag(self, ref, name, message):        
        self.run(['tag', name, ref, '-m', message])

    def deletetag(self, name):   
        self.run(['tag', '-d', name])        

       
    def add(self, paths = []):
        commands = ['add']  
        commands.extend(paths)      
        self.run(commands)     
            
    def commit(self, message, paths = []):
        commands = ['commit', '-m']
        commands.append(message)
        commands.extend(paths)
        self.run(commands)               
             
    def diffentryFromString(self,line):
        tokens = line.strip().split(" ")
        path = tokens[0]
        oldref = tokens[1]
        newref = tokens[2]
        return Diffentry(self.repo, oldref, newref, path) 
    
    
    def diff(self, ref, refb):    
        diffs = []
        output = self.run(['diff-tree', ref, refb])    
        for line in output:
            if line != '':
                diffs.append(self.diffentryFromString(line))
        return diffs
    
    def importosm(self, osmfile, add):
        commands = ["osm", "import", osmfile]        
        if add:
            commands.extend(["--add"])
        self.run(commands)
        
    def downloadosm(self, osmurl, bbox):
        commands = ["osm", "download", osmurl, "--bbox"]
        commands.extend([str(c) for c in bbox])                
        self.run(commands)        
        
    def importshp(self, shapefile, add, dest):
        commands = ["shp", "import", shapefile]
        if dest is not None:
            commands.extend(["--dest", dest])
        if add:
            commands.extend(["--add"])
        self.run(commands)
        
    def exportshp(self, ref, path, shapefile):
        refandpath = ref + ":" + path
        self.run(["shp", "export", refandpath, shapefile, "-o"])
        
    def exportsl(self, ref, database):
        self.run(["sl", "export", ref, "exported", "--database", database])
        
    def featuredata(self, ref, path):  
        refandpath = ref + ":" + path      
        output = self.run(["show", "--raw", refandpath])           
        return self.parseattribs(output[2:]) 

    def cat(self, reference):
        return self.run(["cat", reference])

    def applypatch(self, patchfile):
        pass
        
    def parseattribs(self, lines):
        attributes = {}
        iterator = iter(lines)
        while True:
            try:
                name = iterator.next()
                attribtype = iterator.next()
                value = iterator.next()
                value = self.valuefromstring(value, attribtype)
                attributes[name] = (value, attribtype)
            except StopIteration:
                return attributes 
        
    def valuefromstring(self, value, valuetype):
        if valuetype == "BOOLEAN":
            return str(value).lower() == "true"
        elif valuetype in ["BYTE","SHORT","INTEGER","LONG"]:
            return int(value)
        elif valuetype in ["FLOAT","DOUBLE"]:
            return float(value)
        elif valuetype in ["POINT","LINESTRING","POLYGON","MULTIPOINT","MULTILINESTRING","MULTIPOLYGON"]:            
            try:
                geom = loads(value)
                return geom
            except:
                return value            
        else:
            return value

    def featuresdata(self, refs):
        features = {}
        commands = ["show", "--raw"]
        commands.extend(refs);
        output = self.run(commands)        
        iterator = iter(output)
        lines = []    
        name = None    
        while True:
            try:
                line = iterator.next()
                if line == "":                
                    features[name] = self.parseattribs(lines)   
                    lines = []
                    name = None 
                else:
                    if name is None:
                        name = line
                        iterator.next() #consume id line
                    else: 
                        lines.append(line)   
            except StopIteration:
                break
        if lines:
            features[name] = self.parseattribs(lines)     
        return features

    
    def featurediff(self, ref, ref2, path):
        diffs = {}
        output = self.run(["diff-tree", ref, ref2, "--", path, "--describe"])
        lines = iter(output[1:])
        while True:
            try:
                line = lines.next()
                value1 = None
                value2 = None
                tokens = line.split(" ")
                if len(tokens) == 2:
                    changetype = tokens[0]
                    field = tokens[1]
                    if changetype == "M":
                        value1 = lines.next()
                        value2 = lines.next()
                    elif changetype == "R":
                        value1 = lines.next()
                    elif changetype == "A":
                        value2 = lines.next()
                    else:
                        continue
                    diffs[field] = (value1, value2);
            except StopIteration:
                return diffs    
            
    def blame(self, path):
        attributes = {}
        output = self.run(["blame", path, "--porcelain"])        
        for line in output:
            tokens = line.split(" ")
            name = tokens[0]
            value = " ".join(tokens[6:])
            commitid = tokens[1]
            authorname = tokens[2]
            attributes[name]=(value, commitid, authorname)   
        return attributes 
    
    def merge (self, ref, nocommit = False, message = None):
        commands = ["merge", ref]
        if nocommit:
            commands.append("--no-commit")
        elif message is not None:
            commands.append("-m")
            commands.apend(message)
        self.run(commands) 
        
    def rebase(self, commitish):
        commands = ["rebase", commitish]
        self.run(commands) 
        
    def continuemerge(self):
        pass
    
    def continuerebase(self):
        pass
    
    def abortrebase(self):
        pass
    
    def abortmerge(self):
        pass
        
    def cherrypick(self, commitish):
        commands = ["cherry-pick", commitish]
        self.run(commands)
        
    def show(self, ref):
        commands = ["show", ref]
        return "\n".join(self.run(commands))
    
    def init(self):
        mkdir(self.repo.url)
        self.run(["init"])

    def modifyfeature(self, path, attributes):
        patchfile = self.createpatchfile(path, attributes)
        self.applypatch(patchfile)
        os.remove(patchfile) 

    def createpatchfile(self, path, attributes):               
        f = tempfile.NamedTemporaryFile(delete = False)         
        output = self.run(["show", "--raw", geogit.WORK_HEAD + ":" + path])
        ftId = output[0].split(" ")[0]                
        output = self.cat(ftId)
        f.write("\n".join(output[1:]))            
        f.write("\n")
        oldattributes = self.featuredata(geogit.WORK_HEAD, path)
        for attr in sorted(attributes.iterkeys()):
            try:
                f.write(oldattributes[attr][1] + "\t" + str(attributes[attr]))
            except KeyError, e:
                raise GeoGitException("Attribute %s does not exist in feature to modify" % attr)
        f.close()
        return f.name


def mkdir(newdir):
    newdir = newdir.strip('\n\r ')
    if os.path.isdir(newdir):
        pass
    else:
        (head, tail) = os.path.split(newdir)
        if head and not os.path.isdir(head):
            mkdir(head)
        if tail:
            os.mkdir(newdir)

