import os
import time
import shutil
from geogit.repo import Repository
from geogit.geogitexception import GeoGitException
from geogit.commitish import Commitish
from geogit.diff import TYPE_MODIFIED
from geogit.feature import Feature
import unittest
import geogit
from shapely.geometry import MultiPolygon

class GeogitRepositoryTest(unittest.TestCase):
        
    repo = Repository(os.path.join(os.path.dirname(__file__), 'data/testrepo'))

    def getTempRepoPath(self):
        return os.path.join(os.path.dirname(__file__), "temp", str(time.time())).replace('\\', '/')


    def getClonedRepo(self):
        src = self.repo.url
        dst = self.getTempRepoPath()
        shutil.copytree(src, dst)
        return Repository(dst)

    def testCreateEmptyRepo(self):    
        repoPath =  self.getTempRepoPath()         
        Repository(repoPath, init = True)    
    
    def testRevParse(self):
        headid = self.repo.revparse("HEAD")
        entries = self.repo.log()
        self.assertEquals(entries[0].commitid, headid)

    def testRevParseWrongReference(self):
        try:
            self.repo.revparse("WrOnGReF")
            self.fail()
        except GeoGitException, e:
            pass

    def testLog(self):
        commits = self.repo.log()
        self.assertEquals(4, len(commits))        
        self.assertEquals("message_4", commits[0].message)        
        self.assertEquals("volaya", commits[0].authorname)                
        #TODO: add more 

    def testLogInBranch(self):
        entries = self.repo.log("mybranch")
        self.assertEquals(4, len(entries))

    def testTreesAtHead(self):
        trees = self.repo.trees()
        self.assertEquals(1, len(trees))
        self.assertEquals("parks", trees[0].path)            
        self.assertEquals(geogit.HEAD, trees[0].ref)        
    
    def testTreesAtCommit(self):
        head = self.repo.head()
        parent = head.parent()
        trees = parent.root().trees()
        self.assertEquals(1, len(trees))
        self.assertEquals("parks", trees[0].path)
        entries = self.repo.log()      
        id = self.repo.revparse(trees[0].ref)  
        self.assertEquals(entries[1].commitid, id)   

    def testFeaturesAtHead(self):
        features = self.repo.features(path = "parks")
        self.assertEquals(5, len(features))
        feature = features[0]
        self.assertEquals("parks/5", feature.path)        
        self.assertEquals("HEAD", feature.ref)        

    def testChildren(self):
        children = self.repo.children() 
        self.assertEquals(1, len(children))   
        #TODO improve this test

    def testDiff(self):
        diffs = self.repo.diff(geogit.HEAD, Commitish(self.repo, geogit.HEAD).parent().ref)
        self.assertEquals(1, len(diffs))
        self.assertEquals("parks/5", diffs[0].path)
        self.assertEquals(TYPE_MODIFIED, diffs[0].type())


    def testFeatureData(self):        
        data = self.repo.featuredata(geogit.HEAD, "parks/1")
        self.assertEquals(8, len(data))
        self.assertEquals("Public", data["usage"][0])
        self.assertTrue("owner" in data)
        self.assertTrue("agency" in data)
        self.assertTrue("name" in data)
        self.assertTrue("parktype" in data)
        self.assertTrue("area" in data)
        self.assertTrue("perimeter" in data)
        self.assertTrue("the_geom" in data)
        print "TYPE:" + str(type(data["the_geom"][0]))
        print "TYPE:" + str(data["the_geom"][0])
        self.assertTrue(isinstance(data["the_geom"][0], MultiPolygon))

    def testFeatureDataNonExistentFeature(self):        
        try:
            self.repo.featuredata(geogit.HEAD, "wrongpath/wrongname")
            self.fail()
        except GeoGitException, e:
            pass

    def testAddAndCommit(self):        
        repo = self.getClonedRepo()
        log = repo.log()
        self.assertEqual(4, len(log))
        path = os.path.join(os.path.dirname(__file__), "data", "shp", "1", "parks.shp")
        repo.importshp(path)
        repo.add()
        unstaged = repo.unstaged()
        self.assertFalse(unstaged)
        staged = repo.staged()
        self.assertTrue(staged)
        repo.commit("message")
        staged = repo.staged()
        self.assertFalse(staged)
        log = repo.log()
        self.assertEqual(5, len(log))
        self.assertTrue("message", log[4].message)

    def testCreateReadAndDeleteBranch(self):        
        branches = self.repo.branches()
        self.assertEquals(2, len(branches))
        self.repo.createbranch(geogit.HEAD, "anewbranch")
        branches = self.repo.branches()
        self.assertEquals(3, len(branches))
        names = [c[0] for c in branches]        
        self.assertTrue("anewbranch" in names)
        self.repo.deletebranch("anewbranch")
        branches = self.repo.branches()
        self.assertEquals(2, len(branches))
        names = [c[0] for c in branches]
        self.assertFalse("anewbranch" in names)

    def testGetWrongBranch(self):
        try:
            self.repo.branch("WrOnGReF")
            self.fail()
        except GeoGitException, e:
            pass

    def testBlame(self):
        feature = self.repo.feature(geogit.HEAD, "parks/5")
        blame = self.repo.blame("parks/5")        
        self.assertEquals(8, len(blame))
        attrs = feature.attributes()
        for k,v in blame.iteritems():
            self.assertTrue(v[0], attrs[k])


    def testVersions(self):
        versions = self.repo.versions("parks/5")
        self.assertEquals(2, len(versions))

    def testFeatureDiff(self):
        diff = self.repo.featurediff(geogit.HEAD, geogit.HEAD + "~1", "parks/5")
        self.assertEquals(2, len(diff))
        self.assertTrue("area" in diff)


    def testCreateReadAndDeleteTag(self):
        tags = self.repo.tags()
        self.assertEquals(2, len(tags))
        self.repo.createtag(self.repo.head().ref, "anewtag", "message1")
        tags = self.repo.tags()
        self.assertEquals(3, len(tags))
        names = [tag[0] for tag in tags]
        self.assertTrue("anewtag" in names)
        self.repo.deletetag("anewtag")
        tags = self.repo.tags()
        self.assertEquals(2, len(tags))
        names = [tag[0] for tag in tags]
        self.assertFalse("anewtag" in names)

    def testPatchCreation(self):
        repo = self.getClonedRepo()
        attrs = Feature(repo, geogit.HEAD, "parks/1").attributes()
        attrs["area"] = 1234.5
        patchfile = repo.connector.createpatchfile("parks/1", attrs)
        self.assertTrue(os.path.exists(patchfile))
        #TODO check file content

    def testModifyFeature(self):
        repo = self.getClonedRepo()
        attrs = Feature(repo, geogit.HEAD, "parks/1").attributes()
        attrs["area"] = 1234.5
        repo.modifyfeature("parks/1", attrs)
        attrs = Feature(repo, geogit.WORK_HEAD, "parks/1").attributes()
        self.assertEquals(1234.5, attrs["area"])

    def testModifyFeatureWithWrongFeatureType(self):
        try:
            self.repo.modifyfeature("parks/1", {"field1" : 1, "field2": "a"})
            self.fail()
        except GeoGitException, e:
            pass

    def testConflicts(self):
        repo = self.getClonedRepo()
        repo.merge("mybranch")
        conflicts = repo.conflicts()
        self.assertEquals(1, len(conflicts))
        self.assertEquals('257c8cb9a7eb5ad4740b970bf4e4f901b98042ef:parks/5', conflicts["parks/5"][0]) 
        self.assertEquals('267aafec09e34f289fe9ca9e149ca7f55035bc7a:parks/5', conflicts["parks/5"][1])
        self.assertEquals('02284b8722378a8850e204ffd396bd2f12e3f91f:parks/5', conflicts["parks/5"][2])            