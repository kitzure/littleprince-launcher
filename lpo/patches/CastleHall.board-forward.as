package PrinceOnline.castle
{
   import PrinceOnline.Bridge;
   import PrinceOnline.MapBase;
   import PrinceOnline.ProtectRun;
   import SOL.Utils;
   import flash.external.ExternalInterface;
   import flash.display.*;
   import flash.events.*;
   import flash.utils.*;
   
   public class CastleHall extends MapBase
   {
      
      public var doorReg:MovieClip;
      
      public var doorRank:MovieClip;
      
      public var doorMark:MovieClip;
      
      public var doorLibrary:MovieClip;
      
      public var doorRegHit:MovieClip;
      
      public var doorRankHit:MovieClip;
      
      public var doorLibraryHit:MovieClip;
      
      public var doorPai:MovieClip;
      
      public var solider_a:MovieClip;
      
      public var solider_b:MovieClip;
      
      public function CastleHall()
      {
         super();
         mapWidth = 800;
         mapHeight = 600;
         playerChar.scaleX = playerChar.scaleY = 0.8;
         orderList.push(this.solider_a);
         orderList.push(this.solider_b);
         if(ProtectRun.isOfflineDevMode())
         {
            clickTo = [];
         }
         else
         {
            clickTo = [[bg.board,Bridge.flow.loadNotice]];
         }
         areaTo = [[bg.toReg,Bridge.flow.loadCastleRegister],[bg.toRank,this.rankDoor],[bg.toMark,Bridge.flow.loadCastleMarkRank],[bg.toMapCastle,Bridge.flow.loadMapCastle],[bg.toLibrary,Bridge.flow.loadLibrary]];
         doorOpen = [[bg.doorRegHit,this.doorReg],[bg.doorRankHit,this.doorRank],[bg.doorMarkHit,this.doorMark],[bg.doorLibraryHit,this.doorLibrary]];
         if(Bridge.flow.lastLoadFile == "castle_register.swf")
         {
            px = 190;
            py = 315;
            playerChar.dir = "right";
         }
         else if(Bridge.flow.lastLoadFile == "castle_ranking.swf")
         {
            px = 610;
            py = 315;
         }
         else if(Bridge.flow.lastLoadFile == "library.swf")
         {
            px = 120;
            py = 435;
            playerChar.dir = "right";
         }
         else if(Bridge.flow.lastLoadFile == "castle_mark_ranking.swf")
         {
            px = 670;
            py = 440;
         }
         this.solider_a.visible = false;
         this.solider_b.visible = false;
         this.doorPai.gotoAndStop("lan" + Bridge.user.TextLanguage);
      }
      
      // The web leaderboard replaces the in-game ranking maps: this arch opens
      // the accounts site's board in a new tab.  ExternalInterface is the bridge
      // that works in BOTH players - Ruffle's web player denies navigateToURL
      // (the play page sets openUrlMode "deny"), while real Flash allows it, so
      // the native call stays as the fallback.
      public function rankDoor() : void
      {
         var _url:String = "http://127.0.0.1:8950/web#board";
         var _opened:* = null;
         try
         {
            _opened = ExternalInterface.call("window.open",_url,"_blank");
         }
         catch(_e1:*)
         {
            _opened = null;
         }
         if(_opened == null)
         {
            try
            {
               Utils.getURL(_url,"_blank");
            }
            catch(_e2:*)
            {
            }
         }
      }
   }
}

