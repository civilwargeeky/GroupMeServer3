function toggleClass(object, word) { //Used in searchResults.html
  if (object !== null) {
    if(object.className.indexOf(word) >= 0){
      //Replace the word (and optional space) with a blank string
      object.className = object.className.replace(new RegExp(word + " ?","g"),"");
    } else {
      object.className = word + " " + object.className;
    }
    console.log("New Class Name: ",object.className);
  }
  return object;
}

