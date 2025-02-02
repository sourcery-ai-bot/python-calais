"""
python-calais v.1.4 -- Python interface to the OpenCalais API
Author: Jordan Dimov (jdimov@mlke.net)
Modified: Harshavardhana (harsha@harshavardhana.net)
Last-Update: 03/20/2012
"""

import httplib, urllib, requests, re
import simplejson as json
from StringIO import StringIO
from xml.sax.saxutils import escape

PARAMS_XML = """
<c:params xmlns:c="http://s.opencalais.com/1/pred/" xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"> <c:processingDirectives %s> </c:processingDirectives> <c:userDirectives %s> </c:userDirectives> <c:externalMetadata %s> </c:externalMetadata> </c:params>
"""

STRIP_RE = re.compile('<script.*?</script>|<noscript.*?</noscript>|<style.*?</style>', re.IGNORECASE)

__version__ = "1.4"

class AppURLopener(urllib.FancyURLopener):
    version = "Mozilla/5.0 (X11; U; Linux x86_64; en-US; rv:1.9.0.5) Gecko/2008121623 Ubuntu/8.10 (intrepid)Firefox/3.0.5" # Lie shamelessly to Wikipedia.
urllib._urlopener = AppURLopener()

class Calais():
    """
    Python class that knows how to talk to the OpenCalais API.  Use the analyze() and analyze_url() methods, which return CalaisResponse objects.  
    """
    api_key = None
    processing_directives = {"contentType":"TEXT/RAW", "outputFormat":"application/json", "reltagBaseURL":None, "calculateRelevanceScore":"true", "enableMetadataType":"SocialTags", "discardMetadata":None, "omitOutputtingOriginalText":"true"}
    user_directives = {"allowDistribution":"false", "allowSearch":"false", "externalID":None}
    external_metadata = {}

    def __init__(self, api_key, submitter=f"python-calais client v.{__version__}"):
        self.api_key = api_key
        self.user_directives["submitter"]=submitter

    def _get_params_XML(self):
        return PARAMS_XML % (
            " ".join(
                f'c:{k}="{escape(v)}"'
                for (k, v) in self.processing_directives.items()
                if v
            ),
            " ".join(
                f'c:{k}="{escape(v)}"'
                for (k, v) in self.user_directives.items()
                if v
            ),
            " ".join(
                f'c:{k}="{escape(v)}"'
                for (k, v) in self.external_metadata.items()
                if v
            ),
        )

    def rest_POST(self, content):
        params = urllib.urlencode({'licenseID':self.api_key, 'content':str(content.encode("utf-8")), 'paramsXML':self._get_params_XML()})
        headers = {"Content-type":"application/x-www-form-urlencoded"}
        conn = httplib.HTTPConnection("api.opencalais.com:80")
        conn.request("POST", "/enlighten/rest/", params, headers)
        response = conn.getresponse()
        data = response.read()
        conn.close()
        return (data)

    def get_random_id(self):
        """
        Creates a random 10-character ID for your submission.  
        """
        import string
        from random import choice
        chars = string.letters + string.digits
        np = ""
        for _ in range(10):
            np = np + choice(chars)
        return np

    def get_content_id(self, text):
        """
        Creates a SHA1 hash of the text of your submission.  
        """
        import hashlib
        h = hashlib.sha1()
        h.update(text)
        return h.hexdigest()

    def preprocess_html(self, html):
        html = html.replace('\n', '')
        html = STRIP_RE.sub('', html)
        return html

    def analyze(self, content, content_type="TEXT/RAW", external_id=None):
        if not (content and  len(content.strip())):
            return None
        self.processing_directives["contentType"]=content_type
        if external_id:
            self.user_directives["externalID"] = external_id

        return CalaisResponse(self.rest_POST(content))

    def analyze_url(self, url):
        try:
            f = requests.get(url)
        except:
            print 'Invalid Url %s' % url
            return None

        html = self.preprocess_html(f.text)
        return self.analyze(html, content_type="TEXT/HTML", external_id=None)

    def analyze_file(self, fn):
        import mimetypes
        try:
            filetype = mimetypes.guess_type(fn)[0]
        except:
            raise ValueError(f"Can not determine file type for '{fn}'")
        if filetype == "text/plain":
            content_type="TEXT/RAW"
            with open(fn) as f:
                content = f.read()
        elif filetype == "text/html":
            content_type = "TEXT/HTML"
            with open(fn) as f:
                content = self.preprocess_html(f.read())
        else:
            raise ValueError("Only plaintext and HTML files are currently supported.  ")
        return self.analyze(content, content_type=content_type, external_id=fn)

class CalaisResponse():
    """
    Encapsulates a parsed Calais response and provides easy pythonic access to the data.
    """
    raw_response = None
    simplified_response = None
    
    def __init__(self, raw_result):
        try:
            self.raw_response = json.load(StringIO(raw_result.decode('utf-8', "[removed]")), encoding="utf-8")
        except:
            raise ValueError(raw_result)
        self.simplified_response = self._simplify_json(self.raw_response)
        self.__dict__['doc'] = self.raw_response['doc']
        for k,v in self.simplified_response.items():
            self.__dict__[k] = v

    def _simplify_json(self, json):
        result = {}
        # First, resolve references
        for element in json.values():
            for k,v in element.items():
                if isinstance(v, unicode) and v.startswith("http://") and json.has_key(v):
                    element[k] = json[v]
        for k, v in json.items():
            if v.has_key("_typeGroup"):
                group = v["_typeGroup"]
                if not result.has_key(group):
                    result[group]=[]
                del v["_typeGroup"]
                v["__reference"] = k
                result[group].append(v)
        return result

    def print_summary(self):
        if not hasattr(self, "doc"):
            return None
        info = self.doc['info']
        print "Calais Request ID: %s" % info['calaisRequestID']
        if info.has_key('externalID'): 
            print "External ID: %s" % info['externalID']
        if info.has_key('docTitle'):
            print "Title: %s " % info['docTitle']
        print "Language: %s" % self.doc['meta']['language']
        print "Extractions: "
        for k,v in self.simplified_response.items():
            print "\t%d %s" % (len(v), k)

    def print_entities(self):
        if not hasattr(self, "entities"):
            return None
        for item in self.entities:
            print "%s: %s (%.2f)" % (item['_type'], item['name'], item['relevance'])

    def print_topics(self):
        if not hasattr(self, "topics"):
            return None
        for topic in self.topics:
            print topic['categoryName']

    def print_relations(self):
        if not hasattr(self, "relations"):
            return None
        for relation in self.relations:
            print relation['_type']
            for k,v in relation.items():
                if not k.startswith("_"):
                    if isinstance(v, unicode):
                        print "\t%s:%s" % (k,v)
                    elif isinstance(v, dict) and v.has_key('name'):
                        print "\t%s:%s" % (k, v['name'])

    def print_social_tags(self):
        if not hasattr(self, "socialTag"):
            return None
        for socialTag in self.socialTag:
            print "%s %s" % (socialTag['name'], socialTag['importance'])
