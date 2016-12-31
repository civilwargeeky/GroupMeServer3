//A function for making a new AJAX request. Has actions to complete on success, 404, 500, and other. Passes the requester object to functions
var baseRequest = function(method, parameter, sendData, on200, on404, on500, onOther) {
  var httpRequester = new XMLHttpRequest(); //Make a new one of these
  //Ideally, we will just replace the html in the "userSelection" div with whatever we get here
  httpRequester.responseType = "text"; //This defines what type of data will be returned from the request
  //NOTE: nameVAL should be the user's ID number, not their displayed name!
  httpRequester.open(method, parameter); //Sends a request for the given user's information
  httpRequester.setRequestHeader("Cache-Control", "no-cache"); //Apparently requests will be cached and no data will be resent after stuff is changed
  httpRequester.send(sendData);

  var test = function(func) {
    if (typeof(func) != "function") {
      if ((typeof(func) == "string" && func.length > 0) && func !== null) {
        alert(func);
      }
    } else {
      func(httpRequester);
    }
  };

  httpRequester.onreadystatechange = function() {
    if (httpRequester.readyState == XMLHttpRequest.DONE) { //If we have processed the request
      if (httpRequester.status == 200) { //Our request was successful
        test(on200);
      } else if (httpRequester.status == 404) {
        test(on404);
      } else if (httpRequester.status == 500) {
        test(on500);
      } else {
        test(onOther);
      }
    }
  };
};

var actionRequest = function(parameter, on200, on404, on500, onOther) {return baseRequest("GET", parameter, null, on200, on404, on500, onOther);};

var postRequest = function(parameter, sendData, onAll) {return baseRequest("POST", parameter, sendData, onAll, onAll, onAll, onAll);};