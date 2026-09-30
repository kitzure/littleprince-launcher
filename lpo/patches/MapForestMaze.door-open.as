package PrinceOnline.map
{
   import PrinceOnline.*;
   import flash.display.*;
   import flash.events.*;
   import flash.utils.*;
   
   public class MapForestMaze extends MapBase
   {
      
      public var msg:MovieClip;
      
      public var solider_a:MovieClip;
      
      public var placeName:String = "";
      
      public var sign1:MovieClip;
      
      public function MapForestMaze()
      {
         super();
         this.sign1.gotoAndStop("lan" + Bridge.user.TextLanguage);
         this.placeName = TextLanguage.transLand2()[3];
         orderList.push(this.solider_a);
         orderList.push(this.msg);
         orderList.push(this.sign1);
         mapWidth = 800;
         mapHeight = 600;
         playerChar.scaleX = playerChar.scaleY = 0.8;
         if(Bridge.user.transing)
         {
            px = 205;
            py = 270;
            Bridge.user.transing = false;
            playerChar.gotoAndPlay("back");
            pause = true;
         }
         else if(Bridge.flow.lastLoadFile == "map_forest_toy.swf")
         {
            px = 730;
            py = 250;
         }
         else if(Bridge.flow.lastLoadFile == "maze.swf")
         {
            Bridge.flow.CanGoInMaze = false;
            px = 205;
            py = 270;
            playerChar.dir = "right";
            playerChar.clothInit(Bridge.user);
         }
         this.DoorDetermine(Bridge.flow.CanGoInMaze);
         Bridge.utils.batchAddFrameScript(this.msg,{"loadMsg":this.say});
         doorOpen = [[this.msg.CatHitArea,this.msg]];
      }
      
      public function NewLoadMaze() : *
      {
         RemoteService.addRequest({"type":"inMaze"});
         RemoteService.send();
         Bridge.flow.loadMaze();
      }
      
      public function Determine() : *
      {
         RemoteService.addRequest({"type":"canPlayMaze"});
         RemoteService.send();
      }
      
      public function DoorDetermine(param1:Boolean) : *
      {
         if(true)
         {
            bg.SD.gotoAndStop("door_open");
            bg.road.gotoAndStop(1);
            areaTo = [[bg.toForestToy,Bridge.flow.loadMapForestToy],[bg.toMaze,this.NewLoadMaze]];
         }
      }
      
      public function say() : void
      {
         if(Bridge.user.TextLanguage == 0)
         {
            Bridge.utils.setEmbedFont(this.msg.message,"Shannon Extra Bold ATT",12,"Only visit\nthe maze\n one times a day!");
         }
         else if(Bridge.user.TextLanguage == 1)
         {
            Bridge.utils.setEmbedFont(this.msg.message,"華康儷特圓(P)",15,"每天只能進入\n迷宮一次!");
         }
      }
      
      override public function eEnterFrame(param1:Event) : void
      {
         if(pause)
         {
            press = false;
            keypress = 0;
            key2run = false;
            if(playerChar.currentLabel == "back_end")
            {
               pause = false;
               playerChar.gotoAndPlay("normal");
            }
         }
         if(!pause)
         {
            super.eEnterFrame(param1);
         }
      }
   }
}

